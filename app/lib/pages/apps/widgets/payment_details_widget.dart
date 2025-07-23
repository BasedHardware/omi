import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/add_app_provider.dart';

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
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(12.0),
          ),
          padding: const EdgeInsets.all(14.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(left: 8.0),
                child: Text(
                  'App Cost',
                  style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 6.0),
                margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                decoration: BoxDecoration(
                  color: Color(0xFF35343B),
                  borderRadius: BorderRadius.circular(10.0),
                ),
                width: double.infinity,
                child: TextFormField(
                  keyboardType: TextInputType.number,
                  validator: (value) {
                    if (value != null && value.isNotEmpty) {
                      if (double.tryParse(value) == null) {
                        return 'Please enter a valid amount';
                      }
                      if (double.parse(value) < 1) {
                        return 'Please enter an amount greater than 0';
                      }
                      return null;
                    } else {
                      return null;
                    }
                  },
                  controller: appPricingController,
                  decoration: InputDecoration(
                    prefixIconConstraints: const BoxConstraints(
                      maxHeight: 28,
                      maxWidth: 28,
                    ),
                    prefixIcon: Padding(
                      padding: const EdgeInsets.only(right: 4.0),
                      child: Text(
                        '\$',
                        style: TextStyle(color: Colors.grey.shade300, fontSize: 17),
                      ),
                    ),
                    errorText: null,
                    isDense: true,
                    border: InputBorder.none,
                    hintText: '20',
                  ),
                ),
              ),
              const SizedBox(
                height: 16,
              ),
              Padding(
                padding: const EdgeInsets.only(left: 8.0),
                child: Text(
                  'Payment Plan',
                  style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                ),
              ),
              GestureDetector(
                onTap: () {
                  showModalBottomSheet(
                    context: context,
                    isScrollControlled: true,
                    shape: const RoundedRectangleBorder(
                      borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
                    ),
                    builder: (context) {
                      return Consumer<AddAppProvider>(builder: (context, provider, child) {
                        return Container(
                          padding: const EdgeInsets.all(16.0),
                          height: MediaQuery.of(context).size.height * 0.3,
                          child: SingleChildScrollView(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const SizedBox(
                                  height: 12,
                                ),
                                const Text(
                                  'Payment Plan',
                                  style: TextStyle(color: Colors.white, fontSize: 18),
                                ),
                                const SizedBox(
                                  height: 18,
                                ),
                                ListView.separated(
                                  separatorBuilder: (context, index) {
                                    return Divider(
                                      color: Colors.grey.shade600,
                                      height: 1,
                                    );
                                  },
                                  shrinkWrap: true,
                                  itemCount: provider.paymentPlans.length,
                                  physics: const NeverScrollableScrollPhysics(),
                                  itemBuilder: (context, index) {
                                    return InkWell(
                                      onTap: () {
                                        provider.setPaymentPlan(provider.paymentPlans[index].id);
                                        Navigator.pop(context);
                                      },
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(vertical: 10),
                                        child: Row(
                                          crossAxisAlignment: CrossAxisAlignment.center,
                                          children: [
                                            const SizedBox(
                                              width: 6,
                                            ),
                                            Text(
                                              provider.paymentPlans[index].title,
                                              style: TextStyle(color: Colors.grey.shade300, fontSize: 16),
                                            ),
                                            const Spacer(),
                                            Checkbox(
                                              value: provider.selectePaymentPlan == provider.paymentPlans[index].id,
                                              onChanged: (value) {
                                                provider.setPaymentPlan(provider.paymentPlans[index].id);
                                                Navigator.pop(context);
                                              },
                                              side: BorderSide(color: Colors.grey.shade300),
                                              shape: const CircleBorder(),
                                            ),
                                          ],
                                        ),
                                      ),
                                    );
                                  },
                                ),
                              ],
                            ),
                          ),
                        );
                      });
                    },
                  );
                },
                child: Container(
                  margin: const EdgeInsets.only(left: 2.0, right: 2.0, top: 10, bottom: 6),
                  padding: const EdgeInsets.symmetric(horizontal: 2.0, vertical: 10.0),
                  decoration: BoxDecoration(
                    color: Color(0xFF35343B),
                    borderRadius: BorderRadius.circular(10.0),
                  ),
                  width: double.infinity,
                  child: Row(
                    children: [
                      const SizedBox(
                        width: 12,
                      ),
                      Text(
                        (paymentPlan?.isNotEmpty == true ? paymentPlan : 'None Selected') ?? 'None Selected',
                        style: TextStyle(color: paymentPlan != null ? Colors.grey.shade100 : Colors.grey.shade400, fontSize: 16),
                      ),
                      const Spacer(),
                      Icon(
                        Icons.arrow_forward_ios_rounded,
                        color: Colors.grey.shade400,
                      ),
                      const SizedBox(
                        width: 12,
                      ),
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
}
