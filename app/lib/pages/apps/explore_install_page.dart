import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/pages/apps/widgets/category_card.dart';
import 'package:friend_private/pages/apps/widgets/filter_sheet.dart';
import 'package:friend_private/pages/apps/list_item.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:provider/provider.dart';

class ExploreInstallPage extends StatelessWidget {
  const ExploreInstallPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<AppProvider>(builder: (context, provider, child) {
      return CustomScrollView(
        slivers: [
          const SliverToBoxAdapter(child: SizedBox(height: 18)),
          SliverToBoxAdapter(
            child: SizedBox(
              height: 50,
              child: Row(
                children: [
                  Padding(
                    padding: const EdgeInsets.only(left: 8.0),
                    child: ChoiceChip(
                      label: Row(
                        children: [
                          const Icon(
                            Icons.filter_list_alt,
                            size: 15,
                          ),
                          const SizedBox(width: 4),
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 6.5),
                            child: Text(
                              'Filter ',
                              style: TextStyle(fontSize: 16),
                            ),
                          ),
                          provider.isFilterActive() ? Text("(${provider.filters.length})") : const SizedBox.shrink(),
                        ],
                      ),
                      selected: false,
                      showCheckmark: true,
                      backgroundColor: Colors.transparent,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      onSelected: (bool selected) {
                        showModalBottomSheet(
                          context: context,
                          isScrollControlled: true,
                          shape: const RoundedRectangleBorder(
                            borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                          ),
                          builder: (context) => const FilterBottomSheet(),
                        ).whenComplete(() {
                          context.read<AppProvider>().filterApps();
                        });
                      },
                    ),
                  ),
                  const SizedBox(
                    width: 12,
                  ),
                  provider.isFilterActive()
                      ? Expanded(
                          child: ListView.separated(
                          scrollDirection: Axis.horizontal,
                          itemBuilder: (ctx, idx) {
                            return ChoiceChip(
                              labelPadding: const EdgeInsets.only(left: 8),
                              label: Row(
                                children: [
                                  Padding(
                                    padding: EdgeInsets.symmetric(vertical: 6.5),
                                    child: Text(
                                      provider.filters.values.elementAt(idx),
                                      style: const TextStyle(fontSize: 16),
                                    ),
                                  ),
                                  const SizedBox(width: 6),
                                  const Icon(
                                    Icons.close,
                                    size: 15,
                                  ),
                                ],
                              ),
                              selected: false,
                              showCheckmark: true,
                              backgroundColor: Colors.transparent,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8),
                              ),
                              onSelected: (bool selected) {
                                provider.removeFilter(provider.filters.keys.elementAt(idx));
                              },
                            );
                          },
                          separatorBuilder: (ctx, idx) {
                            return const SizedBox(
                              width: 10,
                            );
                          },
                          itemCount: provider.filters.length,
                        ))
                      : SizedBox(
                          width: MediaQuery.sizeOf(context).width * 0.72,
                          height: 40,
                          child: TextFormField(
                            onChanged: (value) {
                              provider.searchQuery = value;
                              provider.filterApps();
                            },
                            decoration: InputDecoration(
                              hintText: 'Search apps',
                              hintStyle: const TextStyle(color: Colors.white),
                              filled: true,
                              fillColor: Colors.grey[800],
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(8),
                                borderSide: BorderSide.none,
                              ),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 12),
                            ),
                            style: const TextStyle(color: Colors.white),
                          ),
                        )
                ],
              ),
            ),
          ),
          provider.isFilterActive()
              ? const SliverToBoxAdapter(child: SizedBox.shrink())
              : const SliverToBoxAdapter(
                  child: SizedBox(
                  height: 10,
                )),
          !provider.isFilterActive()
              ? const SliverToBoxAdapter(child: SizedBox.shrink())
              : Consumer<AppProvider>(
                  builder: (context, provider, child) {
                    return SliverList(
                      delegate: SliverChildBuilderDelegate(
                        (context, index) {
                          return AppListItem(
                            app: provider.filteredApps[index],
                            index: index,
                          );
                        },
                        childCount: provider.filteredApps.length,
                      ),
                    );
                  },
                ),
          !provider.isFilterActive()
              ? SliverToBoxAdapter(
                  child: CategoryCard(
                    title: 'Popular Apps',
                    apps: context
                        .read<AppProvider>()
                        .apps
                        .where((p) => (p.installs > 50 && (p.ratingAvg ?? 0.0) > 4.0))
                        .toList(),
                  ),
                )
              : const SliverToBoxAdapter(child: SizedBox.shrink()),
          const SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.only(left: 12.0, top: 18, bottom: 0),
              child: Text('All Apps', style: TextStyle(fontSize: 18)),
            ),
          ),
          Selector<AppProvider, List<App>>(
            selector: (context, provider) => provider.apps,
            builder: (context, memoryIntegrationApps, child) {
              return SliverList(
                delegate: SliverChildBuilderDelegate(
                  (context, index) {
                    return AppListItem(
                      app: memoryIntegrationApps[index],
                      index: index,
                    );
                  },
                  childCount: memoryIntegrationApps.length,
                ),
              );
            },
          ),
        ],
      );
    });
  }
}
