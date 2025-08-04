import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

class ActionItemShimmerWidget extends StatelessWidget {
  const ActionItemShimmerWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Shimmer.fromColors(
      baseColor: Colors.grey[800]!,
      highlightColor: Colors.grey[600]!,
      child: Container(
        height: 60,
        width: double.infinity,
        decoration: BoxDecoration(
          color: Colors.grey[800],
          borderRadius: BorderRadius.circular(16),
        ),
      ),
    );
  }
}

class ActionItemsShimmerList extends StatelessWidget {
  final int itemCount;

  const ActionItemsShimmerList({
    super.key,
    this.itemCount = 8,
  });

  @override
  Widget build(BuildContext context) {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          return const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: ActionItemShimmerWidget(),
          );
        },
        childCount: itemCount,
      ),
    );
  }
}

class ActionItemGroupShimmerWidget extends StatelessWidget {
  const ActionItemGroupShimmerWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Column(
        children: [
          // Group header shimmer
          const ActionItemShimmerWidget(),
          const SizedBox(height: 8),
          // Action items shimmer
          ...List.generate(2, (index) => const Padding(
            padding: EdgeInsets.only(bottom: 8),
            child: ActionItemShimmerWidget(),
          )),
        ],
      ),
    );
  }
}

class ActionItemsGroupedShimmerList extends StatelessWidget {
  final int groupCount;

  const ActionItemsGroupedShimmerList({
    super.key,
    this.groupCount = 3,
  });

  @override
  Widget build(BuildContext context) {
    return SliverList(
      delegate: SliverChildBuilderDelegate(
        (context, index) {
          return const ActionItemGroupShimmerWidget();
        },
        childCount: groupCount,
      ),
    );
  }
}