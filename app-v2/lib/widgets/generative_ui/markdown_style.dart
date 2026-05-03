import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import 'package:nooto_v2/theme/app_theme.dart';

/// Shared markdown stylesheet to ensure consistent styling across the
/// generative UI. Adapted to app-v2's design tokens (AppColors, AppStyles).
class MarkdownStyleHelper {
  static MarkdownStyleSheet getStyleSheet(BuildContext context) {
    final style = const TextStyle(
      inherit: false,
      color: AppColors.textPrimary,
      fontSize: 16,
      height: 1.5,
      fontStyle: FontStyle.normal,
      fontWeight: FontWeight.normal,
      letterSpacing: 0,
      wordSpacing: 0,
      textBaseline: TextBaseline.alphabetic,
      decoration: TextDecoration.none,
    );

    return MarkdownStyleSheet(
      p: style,
      pPadding: const EdgeInsets.only(bottom: AppStyles.spacingM),
      a: style.copyWith(decoration: TextDecoration.underline),
      em: style.copyWith(color: AppColors.textTertiary),
      strong: style.copyWith(fontWeight: FontWeight.bold),
      del: style.copyWith(decoration: TextDecoration.lineThrough),
      blockquote: style.copyWith(color: AppColors.textSecondary),
      blockquoteDecoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        border: const Border(left: BorderSide(color: AppColors.brandPrimary, width: 3)),
        borderRadius: const BorderRadius.only(topRight: Radius.circular(4), bottomRight: Radius.circular(4)),
      ),
      blockquotePadding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      code: style.copyWith(backgroundColor: AppColors.backgroundTertiary, fontFamily: 'monospace', fontSize: 14),
      codeblockDecoration: BoxDecoration(
        color: AppColors.backgroundTertiary,
        borderRadius: BorderRadius.circular(AppStyles.radiusSmall),
      ),
      codeblockPadding: const EdgeInsets.all(AppStyles.spacingM),
      h1: style.copyWith(fontSize: 24, fontWeight: FontWeight.bold),
      h2: style.copyWith(fontSize: 22, fontWeight: FontWeight.bold),
      h3: style.copyWith(fontSize: 20, fontWeight: FontWeight.bold),
      h4: style.copyWith(fontSize: 18, fontWeight: FontWeight.bold),
      h5: style.copyWith(fontSize: 16, fontWeight: FontWeight.bold),
      h6: style.copyWith(fontSize: 14, fontWeight: FontWeight.bold),
      h1Padding: const EdgeInsets.only(bottom: AppStyles.spacingM),
      h2Padding: const EdgeInsets.only(bottom: 10),
      h3Padding: const EdgeInsets.only(bottom: AppStyles.spacingS),
      h4Padding: const EdgeInsets.only(bottom: 6),
      h5Padding: const EdgeInsets.only(bottom: AppStyles.spacingXS),
      h6Padding: const EdgeInsets.only(bottom: AppStyles.spacingXS),
      listBullet: style,
      listBulletPadding: const EdgeInsets.only(right: AppStyles.spacingXS),
      listIndent: 8.0,
      textScaler: TextScaler.noScaling,
      tableHead: style.copyWith(fontWeight: FontWeight.bold),
      tableBody: style,
      tableBorder: TableBorder.all(color: Colors.white.withValues(alpha: 0.1)),
      tableColumnWidth: const FlexColumnWidth(),
      tableCellsPadding: const EdgeInsets.all(AppStyles.spacingS),
      horizontalRuleDecoration: BoxDecoration(
        border: Border(top: BorderSide(color: Colors.white.withValues(alpha: 0.08), width: 0.5)),
      ),
      blockSpacing: AppStyles.spacingS,
      checkbox: style,
    );
  }
}
