import 'package:friend_private/backend/http/api/facts.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/base_provider.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:tuple/tuple.dart';
import 'package:uuid/uuid.dart';

class FactsProvider extends BaseProvider {
  List<Fact> facts = [];
  List<Fact> filteredFacts = [];
  List<Tuple2<FactCategory, int>> categories = [];
  FactCategory? selectedCategory;
  String searchQuery = '';

  List<Fact> get unreviewed => facts.where((f) => !f.reviewed).toList();

  void setCategory(FactCategory? category) {
    selectedCategory = category;
    _filterFacts();
    notifyListeners();
  }

  void setSearchQuery(String query) {
    searchQuery = query.toLowerCase();
    _filterFacts();
    notifyListeners();
  }

  void _filterFacts() {
    if (searchQuery.isNotEmpty) {
      filteredFacts = facts.where((fact) => fact.content.decodeString.toLowerCase().contains(searchQuery)).toList();
    } else {
      filteredFacts =
          selectedCategory == null ? facts : facts.where((fact) => fact.category == selectedCategory).toList();
    }
    filteredFacts.sort((a, b) => b.createdAt.compareTo(a.createdAt));
  }

  void _setCategories() {
    categories = FactCategory.values.map((category) {
      final count = facts.where((fact) => fact.category == category).length;
      return Tuple2(category, count);
    }).toList();
    _filterFacts();
    notifyListeners();
  }

  Future<void> init() async {
    await loadFacts();
  }

  Future loadFacts() async {
    loading = true;
    notifyListeners();
    facts = await getFacts();
    loading = false;
    _setCategories();
  }

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
      edited: false,
      reviewed: false,
      userReview: null,
      conversationId: null,
      conversationCategory: null,
      deleted: false,
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

  void reviewFact(Fact fact, bool approved) async {
    var idx = facts.indexWhere((f) => f.id == fact.id);
    if (idx != -1) {
      fact.reviewed = true;
      fact.userReview = approved;
      if (!approved) {
        fact.deleted = true;
        facts.removeAt(idx);
        deleteFactProvider(fact);
      } else {
        facts[idx] = fact;
      }
      _setCategories();
      notifyListeners();
    }
  }
}
