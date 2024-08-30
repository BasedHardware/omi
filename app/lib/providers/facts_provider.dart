import 'package:friend_private/backend/http/api/facts.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';

class FactsProvider extends BaseProvider {
  List<Fact> facts = [];
  List<Tuple2<FactCategory, int>> categories = [];
  FactCategory? selectedCategory;

  void setCategory(FactCategory? category) {
    selectedCategory = category;
    notifyListeners();
  }

  void _setCategories() {
    categories = FactCategory.values.map((category) {
      final count = facts.where((fact) => fact.category == category).length;
      return Tuple2(category, count);
    }).toList();
  }

  void init() async {
    loading = true;
    notifyListeners();
    facts = await getFacts();
    _setCategories();
    // startCreateFactProvider();
    loading = false;
    notifyListeners();
  }

  void reviewFactProvider(int idx, bool value) async {
    var fact = facts[idx];
    reviewFact(fact.id, value);
    fact.reviewed = true;
    fact.userReview = value;
    if (!value) {
      facts.removeAt(idx);
    } else {
      facts[idx] = fact;
    }
    _setCategories();
    notifyListeners();
  }

  void deleteFactProvider(int idx) async {
    var fact = facts[idx];
    deleteFact(fact.id);
    facts.removeAt(idx);
    _setCategories();
    notifyListeners();
  }

  void startCreateFactProvider() {
    facts.insert(
        0,
        Fact(
          id: '',
          uid: SharedPreferencesUtil().uid,
          content: '',
          category: FactCategory.hobbies,
          createdAt: DateTime.now(),
          updatedAt: DateTime.now(),
        ));
    notifyListeners();
  }

  void createFactProvider(String content, FactCategory category) async {
    createFact(content, category);
    facts.add(Fact(
      id: const Uuid().v4(),
      uid: SharedPreferencesUtil().uid,
      content: content,
      category: category,
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    ));
    _setCategories();
    notifyListeners();
  }

  void editFactProvider(int idx, String value) async {
    var fact = facts[idx];
    editFact(fact.id, value);
    fact.content = value;
    fact.updatedAt = DateTime.now();
    facts[idx] = fact;
    _setCategories();
   notifyListeners();
  }
}
