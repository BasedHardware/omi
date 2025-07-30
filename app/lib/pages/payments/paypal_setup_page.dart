import 'package:flutter/material.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/payments/payment_method_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/widgets/animated_loading_button.dart';
import 'package:provider/provider.dart';

import '../../utils/other/validators.dart';

class PaypalSetupPage extends StatefulWidget {
  const PaypalSetupPage({
    super.key,
  });

  @override
  State<PaypalSetupPage> createState() => _PaypalSetupPageState();
}

class _PaypalSetupPageState extends State<PaypalSetupPage> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _paypalMeLinkController = TextEditingController();

  bool _isLoading = false;
  bool _isComplete = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = context.read<PaymentMethodProvider>();
      if (provider.paypalDetails != null) {
        _emailController.text = provider.paypalDetails!.email;
        _paypalMeLinkController.text = provider.paypalDetails!.link;
        setState(() => _isComplete = true);
      }
    });
  }

  String? _validateEmail(String? value) {
    if (value == null || value.isEmpty) {
      return 'Please enter your PayPal email';
    }
    if (!RegExp(r'^[\w-\.]+@([\w-]+\.)+[\w-]{2,4}$').hasMatch(value)) {
      return 'Please enter a valid email address';
    }
    return null;
  }

  String? _validatePaypalMeLink(String? value) {
    if (value == null || value.isEmpty) {
      return 'Please enter your PayPal.me link';
    }
    if (value.toLowerCase().startsWith('http') || value.toLowerCase().startsWith('www')) {
      return 'Do not include http or https or www in the link';
    }
    if (!value.toLowerCase().startsWith('paypal.me/')) {
      return 'Please enter a valid PayPal.me link';
    }
    if (!isValidPayPalMeUrl(value)) {
      return 'Please enter a valid paypal.me link';
    }
    return null;
  }

  @override
  void dispose() {
    _emailController.dispose();
    _paypalMeLinkController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        title: Text(_isComplete ? 'Update PayPal' : 'Set Up PayPal', style: const TextStyle(color: Colors.white, fontSize: 20)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        elevation: 0,
      ),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              child: Padding(
                padding: const EdgeInsets.all(24.0),
                child: Form(
                  key: _formKey,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        child: Column(
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const SizedBox(width: 8),
                                Container(
                                  padding: const EdgeInsets.all(10),
                                  decoration: BoxDecoration(
                                    color: Colors.grey[800],
                                    shape: BoxShape.circle,
                                  ),
                                  child: Image.asset(
                                    Assets.images.herologo.path,
                                    width: 26,
                                    color: Colors.white,
                                  ),
                                ),
                                Transform.translate(
                                  offset: const Offset(-8, 0),
                                  child: Container(
                                    padding: const EdgeInsets.all(10),
                                    decoration: const BoxDecoration(
                                      color: Colors.white,
                                      shape: BoxShape.circle,
                                    ),
                                    child: Image.network(
                                      'https://www.paypalobjects.com/webstatic/icon/pp258.png',
                                      width: 26,
                                      height: 26,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 24),
                            Text(
                              _isComplete ? 'Update your PayPal account details' : 'Connect your PayPal account to start receiving payments for your apps',
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                color: Colors.grey.shade300,
                                fontSize: 16,
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 24),
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1F1F25),
                          borderRadius: BorderRadius.circular(16),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Padding(
                              padding: const EdgeInsets.only(left: 8.0),
                              child: Text(
                                'PayPal Email',
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
                                controller: _emailController,
                                validator: _validateEmail,
                                enabled: !_isLoading,
                                decoration: const InputDecoration(
                                  error: null,
                                  errorText: null,
                                  isDense: true,
                                  border: InputBorder.none,
                                  hintText: 'nik@example.com',
                                ),
                              ),
                            ),
                            const SizedBox(height: 20),
                            Padding(
                              padding: const EdgeInsets.only(left: 8.0),
                              child: Text(
                                'PayPal.me Link',
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
                                controller: _paypalMeLinkController,
                                validator: _validatePaypalMeLink,
                                enabled: !_isLoading,
                                decoration: const InputDecoration(
                                  error: null,
                                  errorText: null,
                                  isDense: true,
                                  border: InputBorder.none,
                                  hintText: 'paypal.me/nik',
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      if (!_isComplete) ...[
                        const SizedBox(height: 24),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: const Color(0xFF1F1F25),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: Color(0xFF35343B),
                              width: 1,
                            ),
                          ),
                          child: const Row(
                            children: [
                              Icon(
                                Icons.info_outline,
                                color: Colors.white70,
                                size: 24,
                              ),
                              SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  'If Stripe is available in your country, we highly recommend using it for faster and easier payouts.',
                                  style: TextStyle(
                                    color: Colors.white70,
                                    fontSize: 14,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: Container(
        padding: const EdgeInsets.only(bottom: 48, left: 24, right: 24),
        child: AnimatedLoadingButton(
          onPressed: () async {
            if (_formKey.currentState!.validate()) {
              setState(() => _isLoading = true);
              MixpanelManager().track(_isComplete ? 'Update PayPal Details' : 'Save PayPal Details');
              await context.read<PaymentMethodProvider>().connectPayPal(
                    _emailController.text.trim(),
                    _paypalMeLinkController.text.trim(),
                  );

              setState(() {
                _isLoading = false;
                _isComplete = true;
              });
            }
          },
          text: _isComplete ? 'Update PayPal Details' : 'Save PayPal Details',
          loaderColor: Colors.black,
          width: MediaQuery.of(context).size.width * 0.8,
          textStyle: const TextStyle(
            color: Colors.black,
            fontSize: 16,
            fontWeight: FontWeight.w500,
          ),
          color: Colors.white,
        ),
      ),
    );
  }
}
