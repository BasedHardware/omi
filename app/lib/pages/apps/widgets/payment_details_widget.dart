import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class PaymentDetailsWidget extends StatelessWidget {
  final TextEditingController appPricingController;
  final String? paymentPlan;
  const PaymentDetailsWidget({super.key, required this.appPricingController, this.paymentPlan});

  @override
  Widget build(BuildContext context) {
    return Form(
      key: Provider.of<AddAppProvider>(context).pricingKey,
      onChanged: () {
        Provider.of<AddAppProvider>(context, listen: false).checkValidity();
      },
      child: Padding(
        padding: const EdgeInsets.only(top: 12.0),
        child: Container(
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
          padding: const EdgeInsets.all(14.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(left: 8.0),
                child:
                    Text(context.l10n.paymentAppCost, style: OmiType.callout.copyWith(color: OmiColors.textSecondary)),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 6.0),
                margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                width: double.infinity,
                child: TextFormField(
                  keyboardType: TextInputType.number,
                  validator: (value) {
                    if (value != null && value.isNotEmpty) {
                      if (double.tryParse(value) == null) {
                        return context.l10n.paymentEnterValidAmount;
                      }
                      if (double.parse(value) < 1) {
                        return context.l10n.paymentEnterAmountGreaterThanZero;
                      }
                      return null;
                    } else {
                      return null;
                    }
                  },
                  controller: appPricingController,
                  decoration: InputDecoration(
                    prefixIconConstraints: const BoxConstraints(maxHeight: 28, maxWidth: 28),
                    prefixIcon: Padding(
                      padding: const EdgeInsets.only(right: 4.0),
                      child: Text('\$', style: OmiType.body.copyWith(color: OmiColors.textSecondary)),
                    ),
                    errorText: null,
                    isDense: true,
                    border: InputBorder.none,
                    hintText: '20',
                  ),
                ),
              ),
              const SizedBox(height: 16),
              Padding(
                padding: const EdgeInsets.only(left: 8.0),
                child: Text(context.l10n.paymentPlan, style: OmiType.callout.copyWith(color: OmiColors.textSecondary)),
              ),
              GestureDetector(
                onTap: () => _showPlanPicker(context),
                child: Container(
                  margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                  padding: const EdgeInsets.symmetric(horizontal: 2.0, vertical: 10.0),
                  decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.mdAll),
                  width: double.infinity,
                  child: Row(
                    children: [
                      const SizedBox(width: 12),
                      Text(
                        (paymentPlan?.isNotEmpty == true ? paymentPlan : context.l10n.paymentNoneSelected) ??
                            context.l10n.paymentNoneSelected,
                        style: OmiType.callout.copyWith(
                          color: paymentPlan != null ? OmiColors.textPrimary : OmiColors.textTertiary,
                        ),
                      ),
                      const Spacer(),
                      const Icon(Icons.arrow_forward_ios_rounded, color: OmiColors.textTertiary),
                      const SizedBox(width: 12),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showPlanPicker(BuildContext context) {
    showOmiSheet<void>(
      context: context,
      title: context.l10n.paymentPlan,
      builder: (context) => Consumer<AddAppProvider>(
        builder: (context, provider, child) {
          return ListView.separated(
            shrinkWrap: true,
            itemCount: provider.paymentPlans.length,
            separatorBuilder: (context, index) => const Divider(color: OmiColors.border, height: 1),
            itemBuilder: (context, index) {
              final plan = provider.paymentPlans[index];
              void select() {
                provider.setPaymentPlan(plan.id);
                Navigator.pop(context);
              }

              return InkWell(
                onTap: select,
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 10),
                  child: Row(
                    children: [
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(plan.title, style: OmiType.callout.copyWith(color: OmiColors.textSecondary)),
                      ),
                      Checkbox(
                        value: provider.selectePaymentPlan == plan.id,
                        onChanged: (_) => select(),
                        side: const BorderSide(color: OmiColors.textSecondary),
                        shape: const CircleBorder(),
                      ),
                    ],
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
