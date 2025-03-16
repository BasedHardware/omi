import 'package:omi/backend/http/api/facts.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/providers/base_provider.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';

class FactsProvider extends BaseProvider {
  List<Fact> facts = [];
  List<Fact> filteredFacts = [];
  List<Tuple2<FactCategory, int>> categories = [];
  FactCategory? selectedCategory;

  void setCategory(FactCategory? category) {
    selectedCategory = category;
    filteredFacts = category == null ? facts : facts.where((fact) => fact.category == category).toList();
    filteredFacts.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    notifyListeners();
  }

  void _setCategories() {
    categories = FactCategory.values.map((category) {
      final count = facts.where((fact) => fact.category == category).length;
      return Tuple2(category, count);
    }).toList();
    setCategory(selectedCategory); // refresh
    notifyListeners();
  }

  void init() async {
    loadFacts();
  }

  Future loadFacts() async {
    loading = true;
    notifyListeners();
    facts = await getFacts();
    loading = false;
    _setCategories();
  }

  // void reviewFactProvider(int idx, bool value) async {
  //   var fact = facts[idx];
  //   reviewFact(fact.id, value);
  //   fact.reviewed = true;
  //   fact.userReview = value;
  //   if (!value) {
  //     facts.removeAt(idx);
  //   } else {
  //     facts[idx] = fact;
  //   }
  //   _setCategories();
  //   notifyListeners();
  // }

  void deleteFactProvider(Fact fact) async {
    deleteFact(fact.id);
    facts.remove(fact);
    _setCategories();
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
      manuallyAdded: true,
    ));
    _setCategories();
  }

  void editFactProvider(Fact fact, String value, FactCategory category) async {
    var idx = facts.indexWhere((f) => f.id == fact.id);
    editFact(fact.id, value);
    fact.content = value;
    fact.category = category;
    fact.updatedAt = DateTime.now();
    fact.edited = true;
    facts[idx] = fact;
    _setCategories();
  }
}
