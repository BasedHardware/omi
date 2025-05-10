import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';
import 'package:omi/backend/http/api/payments.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/widgets/extensions/string.dart';

import 'models/payment_method_config.dart';

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
  bool _isLoading = false;
  PaymentConnectionState _stripeConnectionState = PaymentConnectionState.notConnected;
  PaymentConnectionState _payPalConnectionState = PaymentConnectionState.notConnected;

  List<Map<String, dynamic>> _supportedCountries = [];
  List<Map<String, dynamic>> _filteredCountries = [];
  String _searchQuery = '';

  PayPalDetails? paypalDetails;

  List<Map<String, dynamic>> get supportedCountries => _supportedCountries;
  List<Map<String, dynamic>> get filteredCountries => _filteredCountries;
  String get searchQuery => _searchQuery;

  PaymentMethodType? get activeMethod => _activeMethod;
  PaymentConnectionState get stripeConnectionState => _stripeConnectionState;
  bool get isStripeConnected => _stripeConnectionState == PaymentConnectionState.connected;
  bool get isStripePolling => _isStripePolling;
  bool get isPayPalConnected => _payPalConnectionState == PaymentConnectionState.connected;
  bool get isLoading => _isLoading;

  Future getSupportedCountries() async {
    _isLoading = true;
    var res = await getStripeSupportedCountries();
    _isLoading = false;
    if (res != null) {
      _supportedCountries = res.cast<Map<String, dynamic>>();
      _filteredCountries = _supportedCountries;
      notifyListeners();
    } else {
      AppSnackbar.showSnackbarError('Failed to fetch supported countries. Please try again later.');
    }
  }

  void updateSearchQuery(String query) {
    _searchQuery = query.toLowerCase();
    if (_searchQuery.isEmpty) {
      _filteredCountries = _supportedCountries;
    } else {
      _filteredCountries = _supportedCountries.where((country) {
        return country['name'].toString().toLowerCase().decodeString.contains(_searchQuery);
      }).toList();
    }
    notifyListeners();
  }

  void setActiveMethod(PaymentMethodType method) async {
    _isLoading = true;
    var res = await setDefaultPaymentMethod(method.name);
    _isLoading = false;
    if (res) {
      _activeMethod = method;
      notifyListeners();
    } else {
      AppSnackbar.showSnackbarError('Failed to set default payment method. Please try again later.');
    }
  }

  Future getPaymentMethodsStatus() async {
    _isLoading = true;
    notifyListeners();
    var res = await fetchPaymentMethodsStatus();
    _isLoading = false;
    if (res != null) {
      _payPalConnectionState = getPaymentConnectionState(res['paypal']);
      _stripeConnectionState = getPaymentConnectionState(res['stripe']);
      if (_payPalConnectionState == PaymentConnectionState.connected) {
        getPayPalDetails();
      }
      if (res['default'] != null) {
        _activeMethod = res['default'] == 'stripe' ? PaymentMethodType.stripe : PaymentMethodType.paypal;
      } else {
        _activeMethod = null;
      }
    }
    _isLoading = false;
    notifyListeners();
  }

  Future getPayPalDetails() async {
    var res = await fetchPayPalDetails();
    if (res != null) {
      paypalDetails = res;
      notifyListeners();
    }
  }

  String? _selectedCountryId;
  String? get selectedCountryId => _selectedCountryId;

  void setSelectedCountryId(String countryId) {
    _selectedCountryId = countryId;
    notifyListeners();
  }

  Future<String?> connectStripe() async {
    var res = await getStripeAccountLink(_selectedCountryId);
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
    if (_isStripePolling && _stripeConnectionState != PaymentConnectionState.connected) {
      Future.delayed(const Duration(seconds: 5), () {
        if (_isStripePolling) {
          startStripePolling();
        }
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
