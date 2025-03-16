import 'package:flutter/material.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/facts_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/extensions/functions.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

import 'category_facts_page.dart';
import 'widgets/fact_edit_sheet.dart';
import 'widgets/fact_item.dart';
import 'widgets/fact_dialog.dart';
import 'widgets/fact_review_sheet.dart';

class FactsPage extends StatefulWidget {
  const FactsPage({super.key});

  @override
  State<FactsPage> createState() => FactsPageState();
}

class FactsPageState extends State<FactsPage> {
  final TextEditingController _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  void initState() {
    () async {
      await context.read<FactsProvider>().init();

      final unreviewedFacts = context.read<FactsProvider>().unreviewed;
      if (unreviewedFacts.isNotEmpty) {
        _showReviewSheet(unreviewedFacts);
      }
    }.withPostFrameCallback();
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<FactsProvider>(
      builder: (context, provider, _) {
        return PopScope(
          canPop: true,
          child: Scaffold(
            backgroundColor: Theme.of(context).colorScheme.primary,
            appBar: AppBar(
              backgroundColor: Theme.of(context).colorScheme.primary,
              title: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const Text('My Facts'),
                  const SizedBox(height: 2),
                  Text(
                    '${provider.facts.length} total facts',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade400,
                      fontWeight: FontWeight.normal,
                    ),
                  ),
                ],
              ),
              actions: [
                IconButton(
                  icon: const Icon(Icons.add),
                  onPressed: () {
                    showFactDialog(context, provider);
                    MixpanelManager().factsPageCreateFactBtn();
                  },
                ),
              ],
            ),
            body: provider.loading
                ? const Center(
                    child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ))
                : CustomScrollView(
                    slivers: [
                      SliverToBoxAdapter(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                          child: SearchBar(
                            hintText: 'Search your facts',
                            leading: const Icon(Icons.search, color: Colors.white70),
                            backgroundColor: WidgetStateProperty.all(Colors.grey.shade900),
                            elevation: WidgetStateProperty.all(0),
                            padding: WidgetStateProperty.all(
                              const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                            ),
                            controller: _searchController,
                            trailing: provider.searchQuery.isNotEmpty
                                ? [
                                    IconButton(
                                      icon: const Icon(Icons.close, color: Colors.white70),
                                      onPressed: () {
                                        _searchController.clear();
                                        setState(() {});
                                        provider.setSearchQuery('');
                                      },
                                    )
                                  ]
                                : null,
                            hintStyle: WidgetStateProperty.all(
                              TextStyle(color: Colors.grey.shade400, fontSize: 14),
                            ),
                            shape: WidgetStateProperty.all(
                              RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12),
                              ),
                            ),
                            onChanged: (value) => provider.setSearchQuery(value),
                          ),
                        ),
                      ),
                      if (provider.searchQuery.isEmpty) ...[
                        SliverPadding(
                          padding: const EdgeInsets.fromLTRB(16, 24, 16, 16),
                          sliver: SliverGrid(
                            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                              crossAxisCount: 2,
                              mainAxisSpacing: 12,
                              crossAxisSpacing: 12,
                              childAspectRatio: 1.8,
                            ),
                            delegate: SliverChildBuilderDelegate(
                              (context, index) {
                                final item = provider.categories[index];
                                final category = item.item1;
                                final count = item.item2;

                                return GestureDetector(
                                  onTap: () {
                                    MixpanelManager().factsPageCategoryOpened(category);
                                    provider.setCategory(category);
                                    Navigator.push(
                                      context,
                                      MaterialPageRoute(
                                        builder: (context) => CategoryFactsPage(
                                          category: category,
                                        ),
                                      ),
                                    );
                                  },
                                  child: Container(
                                    decoration: BoxDecoration(
                                      color: Colors.grey.shade900,
                                      borderRadius: BorderRadius.circular(16),
                                    ),
                                    padding: const EdgeInsets.all(16),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          category.toString().split('.').last[0].toUpperCase() +
                                              category.toString().split('.').last.substring(1),
                                          style: const TextStyle(
                                            color: Colors.white,
                                            fontSize: 16,
                                            fontWeight: FontWeight.w500,
                                          ),
                                        ),
                                        const SizedBox(height: 10),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                                          decoration: BoxDecoration(
                                            color: Colors.black26,
                                            borderRadius: BorderRadius.circular(12),
                                          ),
                                          child: Text(
                                            count.toString(),
                                            style: const TextStyle(
                                              color: Colors.white70,
                                              fontSize: 14,
                                              fontWeight: FontWeight.w500,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              },
                              childCount: provider.categories.length,
                            ),
                          ),
                        ),
                      ] else ...[
                        SliverPadding(
                          padding: const EdgeInsets.all(16),
                          sliver: provider.filteredFacts.isEmpty
                              ? SliverFillRemaining(
                                  child: Center(
                                    child: Column(
                                      mainAxisAlignment: MainAxisAlignment.center,
                                      children: [
                                        Icon(Icons.search_off, size: 48, color: Colors.grey.shade600),
                                        const SizedBox(height: 16),
                                        Text(
                                          'No facts found',
                                          style: TextStyle(
                                            color: Colors.grey.shade400,
                                            fontSize: 18,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                )
                              : SliverList(
                                  delegate: SliverChildBuilderDelegate(
                                    (context, index) {
                                      final fact = provider.filteredFacts[index];
                                      return FactItem(
                                        fact: fact,
                                        provider: provider,
                                        onTap: _showQuickEditSheet,
                                      );
                                    },
                                    childCount: provider.filteredFacts.length,
                                  ),
                                ),
                        ),
                      ],
                    ],
                  ),
          ),
        );
      },
    );
  }

  void _showQuickEditSheet(BuildContext context, Fact fact, FactsProvider provider) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => FactEditSheet(
        fact: fact,
        provider: provider,
        onDelete: (_, __, ___) {},
      ),
    );
  }

  void _showReviewSheet(List<Fact> facts) async {
    if (facts.isEmpty) return;
    await showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isDismissible: true,
      enableDrag: false,
      builder: (context) => ListenableProvider(
          create: (_) => FactsProvider(),
          builder: (context, _) {
            return FactReviewSheet(
              facts: facts,
              provider: context.read<FactsProvider>(),
            );
          }),
    );
  }
}
