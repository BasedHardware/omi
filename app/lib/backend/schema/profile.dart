class PayPalDetails {
  final String email;
  final String? paypalMeLink;

  PayPalDetails({
    required this.email,
    this.paypalMeLink,
  });

  factory PayPalDetails.fromJson(Map<String, dynamic> json) {
    return PayPalDetails(
      email: json['paypal_email'],
      paypalMeLink: json['paypal_me_link'] ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'paypal_email': email,
      'paypal_me_link': paypalMeLink ?? '',
    };
  }
}

class CreatorProfile {
  final String creatorName;
  final String creatorEmail;
  final PayPalDetails paypalDetails;
  final bool? isVerified;

  CreatorProfile({
    required this.creatorName,
    required this.creatorEmail,
    required this.paypalDetails,
    this.isVerified,
  });

  factory CreatorProfile.fromJson(Map<String, dynamic> json) {
    return CreatorProfile(
      creatorName: json['creator_name'],
      creatorEmail: json['creator_email'],
      paypalDetails: PayPalDetails.fromJson(json['paypal_details']),
      isVerified: json['is_verified'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'creator_name': creatorName,
      'creator_email': creatorEmail,
      'paypal_details': paypalDetails.toJson(),
      'is_verified': isVerified ?? false,
    };
  }

  bool isEmpty() {
    return creatorName.isEmpty && creatorEmail.isEmpty && paypalDetails.email.isEmpty;
  }

  static CreatorProfile empty() {
    return CreatorProfile(
      creatorName: '',
      creatorEmail: '',
      paypalDetails: PayPalDetails(email: ''),
      isVerified: false,
    );
  }
}

class CreatorStats {
  final int usageCount;
  final double moneyMade;
  final int appsCount;
  final int activeUsers;

  CreatorStats({
    required this.usageCount,
    required this.moneyMade,
    required this.appsCount,
    required this.activeUsers,
  });

  factory CreatorStats.fromJson(Map<String, dynamic> json) {
    var usageCount = json['usage_count'] as Map<String, dynamic>;
    var totalUsage = usageCount.values.fold(0, (prev, element) => (prev + element).toInt());

    var moneyMade = json['money_made'] as Map<String, dynamic>;
    var totalMoneyMade = moneyMade.values.fold(0.0, (prev, element) => (prev + element));
    var activeUsers = json['active_users'] as Map<String, dynamic>;
    var totalActiveUsers = activeUsers.values.fold(0, (prev, element) => (prev + element).toInt());

    return CreatorStats(
      usageCount: totalUsage,
      moneyMade: totalMoneyMade,
      appsCount: json['apps_count'].length,
      activeUsers: totalActiveUsers,
    );
  }
}
