import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/fact.dart';
import 'package:friend_private/providers/facts_provider.dart';
import 'package:friend_private/widgets/extensions/string.dart';

class FactReviewPage extends StatefulWidget {
  final List<Fact> facts;
  final FactsProvider provider;

  const FactReviewPage({
    super.key,
    required this.facts,
    required this.provider,
  });

  @override
  State<FactReviewPage> createState() => _FactReviewPageState();
}

class _FactReviewPageState extends State<FactReviewPage> {
  late List<Fact> remainingFacts;
  late List<Fact> displayedFacts;
  FactCategory? selectedCategory;
  bool isReviewing = false;

  @override
  void initState() {
    super.initState();
    remainingFacts = List.from(widget.facts);
    displayedFacts = List.from(remainingFacts);
  }

  void _filterByCategory(FactCategory? category) {
    setState(() {
      selectedCategory = category;
      displayedFacts =
          category == null ? List.from(remainingFacts) : remainingFacts.where((f) => f.category == category).toList();
    });
  }

  void _saveFact(Fact fact) {
    widget.provider.reviewFact(fact, true);
    setState(() {
      remainingFacts.remove(fact);
      displayedFacts.remove(fact);
    });
    if (remainingFacts.isEmpty) {
      Navigator.pop(context);
    }
  }

  void _discardFact(Fact fact) {
    widget.provider.reviewFact(fact, false);
    setState(() {
      remainingFacts.remove(fact);
      displayedFacts.remove(fact);
    });
    if (remainingFacts.isEmpty) {
      Navigator.pop(context);
    }
  }

  void _saveAll() {
    List<Fact> factsToSave = selectedCategory == null
        ? List.from(remainingFacts)
        : remainingFacts.where((f) => f.category == selectedCategory).toList();

    for (var fact in factsToSave) {
      widget.provider.reviewFact(fact, true);
    }

    setState(() {
      remainingFacts.removeWhere((f) => factsToSave.contains(f));
      displayedFacts = selectedCategory == null
          ? List.from(remainingFacts)
          : remainingFacts.where((f) => f.category == selectedCategory).toList();
    });

    if (remainingFacts.isEmpty) {
      Navigator.pop(context);
    }
  }

  void _discardAll() {
    List<Fact> factsToDiscard = selectedCategory == null
        ? List.from(remainingFacts)
        : remainingFacts.where((f) => f.category == selectedCategory).toList();

    for (var fact in factsToDiscard) {
      widget.provider.reviewFact(fact, false);
    }

    setState(() {
      remainingFacts.removeWhere((f) => factsToDiscard.contains(f));
      displayedFacts = selectedCategory == null
          ? List.from(remainingFacts)
          : remainingFacts.where((f) => f.category == selectedCategory).toList();
    });

    if (remainingFacts.isEmpty) {
      Navigator.pop(context);
    }
  }

  Map<FactCategory, int> get categoryCounts {
    var counts = <FactCategory, int>{};
    for (var fact in remainingFacts) {
      counts[fact.category] = (counts[fact.category] ?? 0) + 1;
    }
    return counts;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const Text('Review Facts'),
            Text(
              '${displayedFacts.length} ${selectedCategory != null ? "in ${selectedCategory.toString().split('.').last}" : "total"}',
              style: TextStyle(
                fontSize: 14,
                color: Colors.grey.shade400,
                fontWeight: FontWeight.normal,
              ),
            ),
          ],
        ),
      ),
      body: Column(
        children: [
          Container(
            height: 50,
            margin: const EdgeInsets.symmetric(vertical: 8),
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16),
              children: [
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: FilterChip(
                    label: Text(
                      'All (${remainingFacts.length})',
                      style: TextStyle(
                        color: selectedCategory == null ? Colors.black : Colors.white70,
                        fontWeight: selectedCategory == null ? FontWeight.w600 : FontWeight.normal,
                      ),
                    ),
                    selected: selectedCategory == null,
                    onSelected: (_) => _filterByCategory(null),
                    backgroundColor: Colors.grey.shade800,
                    selectedColor: Colors.white,
                    checkmarkColor: Colors.black,
                    showCheckmark: false,
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  ),
                ),
                ...categoryCounts.entries.map((entry) {
                  final category = entry.key;
                  final count = entry.value;
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: FilterChip(
                      label: Text(
                        '${category.toString().split('.').last} ($count)',
                        style: TextStyle(
                          color: selectedCategory == category ? Colors.black : Colors.white70,
                          fontWeight: selectedCategory == category ? FontWeight.w600 : FontWeight.normal,
                        ),
                      ),
                      selected: selectedCategory == category,
                      onSelected: (_) => _filterByCategory(category),
                      backgroundColor: Colors.grey.shade800,
                      selectedColor: Colors.white,
                      checkmarkColor: Colors.black,
                      showCheckmark: false,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    ),
                  );
                }),
              ],
            ),
          ),
          Expanded(
            child: displayedFacts.isEmpty
                ? Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.check_circle_outline, size: 48, color: Colors.grey.shade600),
                        const SizedBox(height: 16),
                        Text(
                          selectedCategory == null
                              ? 'All facts have been reviewed'
                              : 'No facts to review in this category',
                          style: TextStyle(
                            color: Colors.grey.shade400,
                            fontSize: 18,
                          ),
                        ),
                      ],
                    ),
                  )
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 80),
                    itemCount: displayedFacts.length,
                    itemBuilder: (context, index) {
                      final fact = displayedFacts[index];
                      return Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        decoration: BoxDecoration(
                          color: Colors.grey.shade900,
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: Colors.white.withOpacity(0.1),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        const Icon(Icons.label_outline, size: 13, color: Colors.white),
                                        const SizedBox(width: 4),
                                        Text(
                                          fact.category.toString().split('.').last,
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontSize: 13,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(height: 12),
                                  Text(
                                    fact.content.decodeString,
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 16,
                                      height: 1.4,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Row(
                              children: [
                                Expanded(
                                  child: TextButton(
                                    style: TextButton.styleFrom(
                                      backgroundColor: Colors.transparent,
                                      shape: const RoundedRectangleBorder(
                                        borderRadius: BorderRadius.only(
                                          bottomLeft: Radius.circular(16),
                                        ),
                                      ),
                                    ),
                                    onPressed: () => _discardFact(fact),
                                    child: Padding(
                                      padding: const EdgeInsets.symmetric(vertical: 12),
                                      child: Row(
                                        mainAxisAlignment: MainAxisAlignment.center,
                                        children: [
                                          Icon(Icons.delete_outline, size: 18, color: Colors.red.shade400),
                                          const SizedBox(width: 8),
                                          Text(
                                            'Discard',
                                            style: TextStyle(
                                              color: Colors.red.shade400,
                                              fontSize: 15,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                                Container(
                                  width: 1,
                                  height: 45,
                                  color: Colors.white.withOpacity(0.1),
                                ),
                                Expanded(
                                  child: TextButton(
                                    style: TextButton.styleFrom(
                                      backgroundColor: Colors.transparent,
                                      shape: const RoundedRectangleBorder(
                                        borderRadius: BorderRadius.only(
                                          bottomRight: Radius.circular(16),
                                        ),
                                      ),
                                    ),
                                    onPressed: () => _saveFact(fact),
                                    child: Padding(
                                      padding: const EdgeInsets.symmetric(vertical: 12),
                                      child: Row(
                                        mainAxisAlignment: MainAxisAlignment.center,
                                        children: [
                                          const Icon(Icons.check, size: 18, color: Colors.white),
                                          const SizedBox(width: 8),
                                          Text(
                                            'Save',
                                            style: TextStyle(
                                              color: Colors.grey.shade100,
                                              fontSize: 15,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),
          if (displayedFacts.isNotEmpty)
            Container(
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary,
                border: Border(
                  top: BorderSide(
                    color: Colors.white.withOpacity(0.1),
                    width: 1,
                  ),
                ),
              ),
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
              child: Row(
                children: [
                  Expanded(
                    child: TextButton(
                      style: TextButton.styleFrom(
                        backgroundColor: Colors.red.shade900.withOpacity(0.3),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      onPressed: _discardAll,
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.delete_outline, size: 18, color: Colors.red.shade400),
                          const SizedBox(width: 8),
                          Text(
                            'Discard all',
                            style: TextStyle(
                              color: Colors.red.shade400,
                              fontSize: 15,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: TextButton(
                      style: TextButton.styleFrom(
                        backgroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      onPressed: _saveAll,
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.check, size: 18, color: Colors.black),
                          const SizedBox(width: 8),
                          const Text(
                            'Save all',
                            style: TextStyle(
                              color: Colors.black,
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
