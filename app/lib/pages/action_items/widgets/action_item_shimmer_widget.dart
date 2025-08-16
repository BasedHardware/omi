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