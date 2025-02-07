import 'package:flutter/material.dart';
import 'package:friend_private/backend/http/api/payments.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';

enum PaymentMethodType {
  stripe,
  paypal,
}

enum PaymentConnectionState {
  connected,
  notConnected,
  inComplete,
}

PaymentConnectionState getPaymentConnectionState(String state) {
  switch (state) {
    case 'connected':
      return PaymentConnectionState.connected;
    case 'incomplete':
      return PaymentConnectionState.inComplete;
    default:
      return PaymentConnectionState.notConnected;
  }
}

class PaymentMethodProvider extends ChangeNotifier {
  PaymentMethodType? _activeMethod;
  bool _isStripePolling = false;
  PaymentConnectionState _stripeConnectionState = PaymentConnectionState.notConnected;
  PaymentConnectionState _payPalConnectionState = PaymentConnectionState.notConnected;

  PaymentMethodType? get activeMethod => _activeMethod;
  bool get isStripeConnected => _stripeConnectionState == PaymentConnectionState.connected;
  bool get isStripePolling => _isStripePolling;
  bool get isPayPalConnected => _payPalConnectionState == PaymentConnectionState.connected;

  void setActiveMethod(PaymentMethodType? method) {
    // if (method == null) {
    //   AppSnackbar.showSnackbarError('You must have at least one payment method active and connected.');
    //   return;
    // }
    if (_activeMethod != method) {
      _activeMethod = method;
      notifyListeners();
    }
  }

  Future getPaymentMethodsStatus() async {
    var res = await fetchPaymentMethodsStatus();
    if (res != null) {
      _payPalConnectionState = getPaymentConnectionState(res['paypal']);
      _stripeConnectionState = getPaymentConnectionState(res['stripe']);
      if (res['default'] != null) {
        _activeMethod = res['default'] == 'stripe' ? PaymentMethodType.stripe : PaymentMethodType.paypal;
      } else {
        _activeMethod = null;
      }
      notifyListeners();
    }
  }

  Future<String?> connectStripe() async {
    var res = await getStripeAccountLink();
    if (res != null) {
      return res['url'];
    }
    return null;
  }

  Future<bool> checkStripeConnectionStatus() async {
    var res = await isStripeOnboardingComplete();
    _stripeConnectionState = res ? PaymentConnectionState.connected : PaymentConnectionState.inComplete;
    notifyListeners();
    return res;
  }

  void startStripePolling() {
    _isStripePolling = true;
    checkStripeConnectionStatus();
    if (!isStripeConnected) {
      Future.delayed(const Duration(seconds: 5), () {
        startStripePolling();
      });
    } else {
      _isStripePolling = false;
    }
    notifyListeners();
  }

  void stopStripePolling() {
    _isStripePolling = false;
    notifyListeners();
  }

  Future<void> connectPayPal(String email, String link) async {
    var res = await savePayPalDetails(email, link);
    if (!res) {
      AppSnackbar.showSnackbarError('Failed to save PayPal details. Please try again later.');
      return;
    }
    _payPalConnectionState = PaymentConnectionState.connected;
    if (!isStripeConnected) {
      _activeMethod = PaymentMethodType.paypal;
    }
    notifyListeners();
  }
}
