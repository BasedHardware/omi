import 'package:flutter/material.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/app_section_card.dart';
import 'package:omi/pages/apps/widgets/filter_sheet.dart';
import 'package:omi/pages/apps/list_item.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/utils/other/debouncer.dart';
import 'package:provider/provider.dart';

import 'widgets/create_options_sheet.dart';

String filterValueToString(dynamic value) {
  if (value.runtimeType == String) {
    return value;
  } else if (value.runtimeType == Category) {
    return (value as Category).title;
  } else if (value.runtimeType == AppCapability) {
    return (value as AppCapability).title;
  }
  return '';
}

class ExploreInstallPage extends StatefulWidget {
  const ExploreInstallPage({super.key});

  @override
  State<ExploreInstallPage> createState() => _ExploreInstallPageState();
}

class _ExploreInstallPageState extends State<ExploreInstallPage> with AutomaticKeepAliveClientMixin {
  late TextEditingController searchController;
  Debouncer debouncer = Debouncer(delay: const Duration(milliseconds: 500));

  @override
  void initState() {
    searchController = TextEditingController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AddAppProvider>().init();
    });
    super.initState();
  }

  @override
  void dispose() {
    searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
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
                    padding: const EdgeInsets.only(left: 12.0),
                    child: Container(
                      decoration: BoxDecoration(
                        color: Colors.grey[800],
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: IconButton(
                        icon: const Icon(
                          Icons.filter_list_alt,
                          size: 20,
                          color: Colors.white,
                        ),
                        onPressed: () {
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
                        tooltip: 'Filter',
                        visualDensity: VisualDensity.compact,
                        constraints: const BoxConstraints(minWidth: 40, minHeight: 40),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  provider.isFilterActive()
                      ? Expanded(
                          child: ListView.separated(
                          scrollDirection: Axis.horizontal,
                          itemBuilder: (ctx, idx) {
                            return Chip(
                              labelPadding: const EdgeInsets.symmetric(horizontal: 4),
                              label: Text(
                                filterValueToString(provider.filters.values.elementAt(idx)),
                                style: const TextStyle(fontSize: 14),
                              ),
                              deleteIcon: const Icon(Icons.close, size: 14),
                              onDeleted: () {
                                provider.removeFilter(provider.filters.keys.elementAt(idx));
                              },
                              backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(8),
                              ),
                              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                            );
                          },
                          separatorBuilder: (ctx, idx) {
                            return const SizedBox(width: 8);
                          },
                          itemCount: provider.filters.length,
                        ))
                      : Expanded(
                          child: SizedBox(
                            height: 40,
                            child: TextFormField(
                              controller: searchController,
                              focusNode: context.read<HomeProvider>().appsSearchFieldFocusNode,
                              onChanged: (value) {
                                debouncer.run(() {
                                  provider.searchApps(value);
                                });
                              },
                              decoration: InputDecoration(
                                hintText: 'Search Apps',
                                hintStyle: TextStyle(color: Colors.white.withOpacity(0.7), fontSize: 14),
                                filled: true,
                                fillColor: Colors.grey[800],
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                  borderSide: BorderSide.none,
                                ),
                                prefixIcon: const Icon(Icons.search, color: Colors.white, size: 20),
                                suffixIcon: provider.isSearchActive()
                                    ? GestureDetector(
                                        onTap: () {
                                          context.read<HomeProvider>().appsSearchFieldFocusNode.unfocus();
                                          provider.searchApps('');
                                          searchController.clear();
                                        },
                                        child: const Icon(
                                          Icons.close,
                                          color: Colors.white,
                                          size: 20,
                                        ),
                                      )
                                    : null,
                                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                                isDense: true,
                              ),
                              style: const TextStyle(color: Colors.white),
                            ),
                          ),
                        ),
                  const SizedBox(width: 12),
                ],
              ),
            ),
          ),
          const SliverToBoxAdapter(
              child: SizedBox(
            height: 20,
          )),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12.0),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('All Apps', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                  ElevatedButton.icon(
                    onPressed: () {
                      showModalBottomSheet(
                        context: context,
                        builder: (context) => const CreateOptionsSheet(),
                        shape: const RoundedRectangleBorder(
                          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                        ),
                      );
                    },
                    icon: const Icon(Icons.add, size: 16),
                    label: const Text('Create'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Theme.of(context).colorScheme.primary.withOpacity(0.9),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      minimumSize: const Size(0, 36),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      elevation: 2,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SliverToBoxAdapter(
              child: SizedBox(
            height: 16,
          )),
          !provider.isFilterActive() && !provider.isSearchActive()
              ? const SliverToBoxAdapter(child: SizedBox.shrink())
              : Consumer<AppProvider>(
                  builder: (context, provider, child) {
                    if (provider.filteredApps.isEmpty) {
                      return SliverToBoxAdapter(
                        child: Padding(
                          padding: EdgeInsets.only(top: MediaQuery.sizeOf(context).height * 0.28),
                          child: const Text(
                            'No apps found',
                            style: TextStyle(fontSize: 18),
                            textAlign: TextAlign.center,
                          ),
                        ),
                      );
                    }
                    return SliverPadding(
                      padding: const EdgeInsets.only(bottom: 64),
                      sliver: SliverList.separated(
                        itemCount: provider.filteredApps.length,
                        itemBuilder: (context, index) {
                          final originalIndex =
                              provider.apps.indexWhere((app) => app.id == provider.filteredApps[index].id);
                          return AppListItem(
                            app: provider.filteredApps[index],
                            index: originalIndex,
                          );
                        },
                        separatorBuilder: (context, index) {
                          return const SizedBox(height: 8);
                        },
                      ),
                    );
                  },
                ),
          !provider.isFilterActive() && !provider.isSearchActive() && context.read<AppProvider>().popularApps.isNotEmpty
              ? SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12.0),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text('Popular Apps', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                        TextButton.icon(
                          onPressed: () {
                            // Could add a "see all popular" action here
                          },
                          icon: const Icon(Icons.arrow_forward, size: 16),
                          label: const Text('See all'),
                          style: TextButton.styleFrom(
                            padding: const EdgeInsets.symmetric(horizontal: 8),
                            minimumSize: const Size(0, 36),
                          ),
                        ),
                      ],
                    ),
                  ),
                )
              : const SliverToBoxAdapter(child: SizedBox.shrink()),
          !provider.isFilterActive() && !provider.isSearchActive() && context.read<AppProvider>().popularApps.isNotEmpty
              ? SliverToBoxAdapter(
                  child: AppSectionCard(
                    title: '',  // Removed title as we have it in the row above
                    apps: context.read<AppProvider>().popularApps,
                  ),
                )
              : const SliverToBoxAdapter(child: SizedBox.shrink()),
          !provider.isFilterActive() && !provider.isSearchActive()
              ? Selector<AppProvider, List<App>>(
                  selector: (context, provider) => provider.apps,
                  builder: (context, apps, child) {
                    return SliverList(
                      delegate: SliverChildBuilderDelegate(
                        (context, index) {
                          return AppListItem(
                            app: apps[index],
                            index: index,
                          );
                        },
                        childCount: apps.length,
                      ),
                    );
                  },
                )
              : const SliverToBoxAdapter(child: SizedBox.shrink()),
        ],
      );
    });
  }

  @override
  bool get wantKeepAlive => true;
}
