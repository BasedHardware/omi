import 'package:friend_private/backend/preferences.dart';
import 'package:gleap_sdk/gleap_sdk.dart';
import 'package:gleap_sdk/models/gleap_user_property_model/gleap_user_property_model.dart';

identifyGleap() {
  Gleap.identifyContact(
    userId: SharedPreferencesUtil().uid,
    userProperties: GleapUserProperty(
      name: SharedPreferencesUtil().fullName,
      email: SharedPreferencesUtil().email,
    ),
  );
}
