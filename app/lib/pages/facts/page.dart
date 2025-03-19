import 'package:flutter/material.dart';
import 'package:omi/backend/schema/fact.dart';
import 'package:omi/providers/facts_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/extensions/functions.dart';
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
            body: provider.loading
                ? const Center(
                    child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                  ))
                : CustomScrollView(
                    slivers: [
                      SliverAppBar(
                        backgroundColor: Theme.of(context).colorScheme.primary,
                        pinned: true,
                        snap: true,
                        floating: true,
                        title: const Text('My Memory'),
                        actions: [
                          IconButton(
                            icon: const Icon(Icons.delete_sweep_outlined),
                            onPressed: () {
                              _showDeleteAllConfirmation(context, provider);
                            },
                          ),
                          IconButton(
                            icon: const Icon(Icons.add),
                            onPressed: () {
                              showFactDialog(context, provider);
                              MixpanelManager().factsPageCreateFactBtn();
                            },
                          ),
                        ],
                        bottom: PreferredSize(
                          preferredSize: const Size.fromHeight(68),
                          child: Padding(
                            padding: const EdgeInsets.fromLTRB(16, 0, 16, 10),
                            child: SearchBar(
                              hintText: 'Search Omi\'s memory about you',
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
                      ),
                      SliverPadding(
                        padding: const EdgeInsets.all(16),
                        sliver: provider.filteredFacts.isEmpty
                            ? SliverFillRemaining(
                                child: Center(
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(Icons.note_add, size: 48, color: Colors.grey.shade600),
                                      const SizedBox(height: 16),
                                      Text(
                                        provider.searchQuery.isEmpty ? 'No facts yet' : 'No facts found',
                                        style: TextStyle(
                                          color: Colors.grey.shade400,
                                          fontSize: 18,
                                        ),
                                      ),
                                      if (provider.searchQuery.isEmpty) ...[
                                        const SizedBox(height: 8),
                                        TextButton(
                                          onPressed: () => showFactDialog(context, provider),
                                          child: const Text('Add your first fact'),
                                        ),
                                      ],
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

  void _showDeleteAllConfirmation(BuildContext context, FactsProvider provider) {
    if (provider.facts.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No facts to delete'),
          duration: Duration(seconds: 2),
        ),
      );
      return;
    }

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: Colors.grey.shade900,
        title: const Text(
          'Clear Omi\'s Memory',
          style: TextStyle(color: Colors.white),
        ),
        content: Text(
          'Are you sure you want to clear Omi\'s memory? This action cannot be undone.',
          style: TextStyle(color: Colors.grey.shade300),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(
              'Cancel',
              style: TextStyle(color: Colors.grey.shade400),
            ),
          ),
          TextButton(
            onPressed: () {
              provider.deleteAllFacts();
              Navigator.pop(context);
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('Omi\'s memory about you has been cleared'),
                  duration: Duration(seconds: 2),
                ),
              );
            },
            child: const Text(
              'Clear Memory',
              style: TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );
  }
}
