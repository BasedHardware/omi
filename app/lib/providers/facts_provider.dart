import 'package:friend_private/backend/http/api/facts.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/base_provider.dart';

class FactsProvider extends BaseProvider {
  List<Fact> facts = [];

  void init() async {
    facts = await getFacts();
    print('facts: ${facts.length}');
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
    notifyListeners();
  }

  void deleteFactProvider(int idx) async {
    var fact = facts[idx];
    deleteFact(fact.id);
    facts.removeAt(idx);
    notifyListeners();
  }
}
