import 'package:flutter/material.dart';

import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:omi/ui/omi_tokens.dart';

class ActionItemShimmerWidget extends StatelessWidget {
  const ActionItemShimmerWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return ShimmerWithTimeout(
      baseColor: OmiColors.surface2,
      highlightColor: OmiColors.surface4,
      child: Container(
        height: 60,
        width: double.infinity,
        decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: BorderRadius.circular(16)),
      ),
    );
  }
}

class ActionItemsShimmerList extends StatelessWidget {
  final int itemCount;

  const ActionItemsShimmerList({super.key, this.itemCount = 8});

  @override
  Widget build(BuildContext context) {
    return SliverList(
      delegate: SliverChildBuilderDelegate((context, index) {
        return const Padding(
          padding: EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: ActionItemShimmerWidget(),
        );
      }, childCount: itemCount),
    );
  }
}
