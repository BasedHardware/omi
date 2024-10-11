import 'dart:convert';

import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/cupertino.dart';

import '../../backend/preferences.dart';
import '../model/user_subscription_model.dart';

class UserSubscriptionFire{
  UserSubscriptionFire() {
    _fs.settings = const Settings(persistenceEnabled: true);
  }

  final _fs = FirebaseFirestore.instance;

  final _coll = "user_subscription";

  Future<void> saveUserSubscription(UserSubscriptionModel data) async {
    
    _fs.collection(_coll).add(data.toJson()).then((snapshot){
      print('------ saveUserSubscription ----');
      print(snapshot);
      if (snapshot.id.isNotEmpty) {
        /*for (final f in snapshot.docs) {

        }
        return saveUserSubscription;*/
      } else {
        return null;
      }
    });
  }

  Future<List<UserSubscriptionModel>?> getUserSubscriptionList() async =>
      _fs.collection(_coll).get(const GetOptions()).then((snapshot) {
        final userSubscriptionModels = <UserSubscriptionModel>[];
        if (snapshot.docs.isNotEmpty) {
          for (final f in snapshot.docs) {
            if(f.data().containsValue(SharedPreferencesUtil().uid)){
              final userSubscriptionModel = UserSubscriptionModel.fromJson(f.data())..userId = SharedPreferencesUtil().uid;
              debugPrint(userSubscriptionModel.userId);
              debugPrint(userSubscriptionModel.createdDate.toString());
              //debugPrint("END getUserSubscriptionList -> $userSubscriptionModel");
              userSubscriptionModels.add(userSubscriptionModel);
            }
          }
          return userSubscriptionModels;
        } else {
          return null;
        }
      });
}