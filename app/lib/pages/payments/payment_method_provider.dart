import 'package:flutter/material.dart';
import 'package:flutter/widgets.dart';

import 'package:omi/backend/http/api/payments.dart';
import 'package:omi/app_globals.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'models/payment_method_config.dart';

enum PaymentMethodType { stripe, paypal }

enum PaymentConnectionState { connected, notConnected, inComplete }

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
  int _sessionGeneration = 0;

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
    final generation = _sessionGeneration;
    _isLoading = true;
    var res = await getStripeSupportedCountries();
    if (generation != _sessionGeneration) return;
    _isLoading = false;
    if (res != null) {
      _supportedCountries = res.cast<Map<String, dynamic>>();
      _filteredCountries = _supportedCountries;
      notifyListeners();
    } else {
      AppSnackbar.showSnackbarError(globalNavigatorKey.currentContext!.l10n.paymentFailedToFetchCountries);
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
    final generation = _sessionGeneration;
    _isLoading = true;
    var res = await setDefaultPaymentMethod(method.name);
    if (generation != _sessionGeneration) return;
    _isLoading = false;
    if (res) {
      _activeMethod = method;
      notifyListeners();
    } else {
      AppSnackbar.showSnackbarError(globalNavigatorKey.currentContext!.l10n.paymentFailedToSetDefault);
    }
  }

  Future getPaymentMethodsStatus() async {
    final generation = _sessionGeneration;
    _isLoading = true;
    notifyListeners();
    var res = await fetchPaymentMethodsStatus();
    if (generation != _sessionGeneration) return;
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
    final generation = _sessionGeneration;
    var res = await fetchPayPalDetails();
    if (generation != _sessionGeneration) return;
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
    final generation = _sessionGeneration;
    var res = await getStripeAccountLink(_selectedCountryId);
    if (generation != _sessionGeneration) return null;
    if (res != null) {
      return res['url'];
    }
    return null;
  }

  Future<bool> checkStripeConnectionStatus() async {
    final generation = _sessionGeneration;
    var res = await isStripeOnboardingComplete();
    if (generation != _sessionGeneration) return false;
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
    final generation = _sessionGeneration;
    var res = await savePayPalDetails(email, link);
    if (generation != _sessionGeneration) return;
    if (!res) {
      AppSnackbar.showSnackbarError(globalNavigatorKey.currentContext!.l10n.paymentFailedToSavePaypal);
      return;
    }
    _payPalConnectionState = PaymentConnectionState.connected;
    if (!isStripeConnected) {
      _activeMethod = PaymentMethodType.paypal;
    }
    notifyListeners();
  }

  void clearUserData() {
    _sessionGeneration++;
    _activeMethod = null;
    _isStripePolling = false;
    _isLoading = false;
    _stripeConnectionState = PaymentConnectionState.notConnected;
    _payPalConnectionState = PaymentConnectionState.notConnected;
    _filteredCountries = _supportedCountries;
    _searchQuery = '';
    _selectedCountryId = null;
    paypalDetails = null;
    notifyListeners();
  }
}
