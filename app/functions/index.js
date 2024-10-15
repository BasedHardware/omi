const functions = require("firebase-functions");
const admin = require('firebase-admin');
var axios = require('axios');
var FCM = require('fcm-node')
var Verifier = require('google-play-billing-validator');
const req = require('request');

const userPremiumCollection = "user_subscription";
const userHistoryCollection = "history";

admin.initializeApp(functions.config().firebase);
var db = admin.firestore();

var notAllowedStatus = ["DID_FAIL_TO_RENEW", "EXPIRED", "GRACE_PERIOD_EXPIRED", "REVOKE", "CANCEL"];

exports.purchaseComplete = functions.https.onRequest((request, response) => {

    if (request.method !== 'POST') {
        response.send({ status: false, message: "Invalid request method" });
        return;
    }

    var userId = request.body.userId;
    var receipt = request.body.receipt;
    var platform = request.body.platform;
    var productId = request.body.productId;
    var purchaseId = request.body.purchaseId;
    var pluginId = request.body.pluginId;

    console.log(request.body);

    if (userId === undefined || receipt === undefined || userId === "" || receipt === "", platform === undefined || platform === "") {
        response.send({ status: false, message: "Missing required parameters" });
        return;
    }

    if (platform === "android" && (productId === undefined || productId === "")) {
        response.send({ status: false, message: "Missing required parameters" });
    }

    db.collection(userPremiumCollection).doc(userId).get().then(async snapshot => {
        if (snapshot) {
            var data = snapshot.data();

            if (platform === "android") {

                var options = {
                    email: 'mailto:revenuecat-subscripton@ai-wearable.iam.gserviceaccount.com',
                    key: '-----BEGIN PRIVATE KEY-----\nMIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQC/Wav+T8Ly69K0\nPJatCLuSdpFL0312kMNFXsyM5rM9NQeYpWP+ufkrRU25RwVVEWf4MwmI8FjyFb/V\nSURlqvqeLxGchbpiTPWqJ2g7U7qt+ncngTo1bQ/9Zd5AkIjUZkGyW8NrsYJl1Oml\n24cy9mJXjRNb9na2gnJllF+GaQPY8G28a5pGMavLwkCiQke+1hx580mleE0ur4lR\nniW/IwRoXTtehVuvt/gjhywRvfpbMUNrG+M37PRYerP7FNl5fGgopdr8jnrFX5zD\nTgHoqr1eYaVIzC0RkNqc6DlWuFw4YNJ7pgnYB4eCzfsPVopemnQAVNROOfSV7Qvp\nIaWJ+bF3AgMBAAECggEAEgciR7L/FID4WIfO0F2ewnVOSh0SWH3aD+qXDf1cTLt2\nzEBk0+Z0ncmJQZf53iJmL8GrN84hKym2aaNeANAjjYy0tZD51vIWQSI2VUSVtXeA\nC2ZG9Cqi04Zp8p5Lbet2bBXuKvLN7Mcq/jfZHImPCV2ewc7OL3LJ0V0xxMmXFbSj\nW9iHJagqRl1PGTUlUmVaRagrIFpm3ctf6lHK5thuXWav6wFvbWg7d5HtLCkp4/fk\nc33fOuI4jr+4UBtf9hDXHE+YosKVdDiHmgweJgwFC2kPh6jIFn1v2wN+KOETsp7I\ng+m7KjoZnKzMY9sxiskMECbOBYwvd0xOqNJWKlLssQKBgQDxzVp0PUH0kit7fEfU\nDztT/gpdsMWJ2D5e78E0rCBbvl7cEaQfVLgZ2Qc3YWrOBA1j6a9j1F5U+Xsx5joF\nNydr6VTQ37pBj1xcDVsYL6/fKm/1YdVnECSyn0a8fS+ToSV1gGqAsWT1pXZrFU7n\ncUEoBIP4RzpFxvYZBQaFNm020QKBgQDKlfObptO7g9I0rWZqK0Ed+dQzRIJefyrW\n2fIed9mf5usPG2cDECfyCNnahfq8Lu6etQIpff2NsHUGvhxlilZDaJpdfw+1/tmH\noFazfCZgmaSnxEoutCNwtxIb4M0GYUV5WmqcfoAUvr9l/byzPixMHtsSiKNj85rN\nxzqIjWIFxwKBgQC/oqShozr2fjH/+AtlQX0foCLPBh5IlR05WIKjIBe1HjdH6qNM\nQXR2584UUhy3kfaazMW4NMNeTSsZ7QDmyUNw/se9ktKmytvECMG9dW3JTHTW4Oak\ne+LZvent0Lk4I2rwqQm/XNhK5wvm6khSnSuqb4m355uDWaAJTDZStUPxQQKBgQCB\nGKuDvfzhWrCClxlTgLrfQkwCW58EXt9KyNospk1NQ5b5KoorfokmCJPjWEuezf2L\nr2dwT3RbbV417MIlxtEP5cGw4P5/CKdQcVGu0OeX2XD+4+wt9Oc8tbzZfRjJ/wSJ\nv59+mHJARgmsEdTFGFKcM3GBTwdn813r0hCv4gDcEwKBgQCsXLMQNZiYR4KIdekG\n1Lk1WUsx6GGIWCsbkOg4lfBGK0oS029S+tFq6mdbDHV3e0HQtpib9wECPfzIdYx5\nrGIGyh+8YwTVNHaoFHl+U84gLOZQW4oGEwU//bQeOQh47Bwh/Of8yUlHtmahZNwl\nvGhsDgl7C9YTf68whbUSytqnGg==\n-----END PRIVATE KEY-----\n'
                };

                var verifier = new Verifier(options);

                var receiptDic = {
                    packageName: "com.ai.wearable",
                    productId: productId,
                    purchaseToken: receipt
                };

                verifier.verifySub(receiptDic).then(function (res) {
                    console.log("res");
                    console.log(res);

                    if ((res.payload.paymentState === undefined || res.payload.paymentState === null) || (res.payload.cancelReason != undefined || res.payload.cancelReason >= 0)) {
                        response.send({ status: false, message: "Subscription has been cancelled or expired" });
                        return;
                    }

                    if (res.payload.paymentState === 0) {
                        response.send({ status: false, message: "Payment pending, please try again" });
                        return;
                    }

                    updateData(
                        pluginId,
                        res.payload.orderId,
                        new Date(parseInt(res.payload.expiryTimeMillis)),
                        userId,
                        response,
                        userPremiumCollection,
                        productId,
                        purchaseId,
                        platform,
                    );
                })
                    .then(function (response) {
                        // Here for example you can chain your work if subscription is valid
                        // eg. add coins to the user profile, etc
                        // If you are new to promises API
                        // Awesome docs: https://developers.google.com/web/fundamentals/primers/promises
                        console.log("response:");
                        console.log(response);
                    })
                    .catch(function (error) {
                        console.log("error");
                        console.log(error);
                        response.send({ status: false, message: "something went wrong please try again" });
                    });
                return;
            }

            var reqBody = {
                "receipt-data": receipt,
                "password": "29edd500911a444787b0f6cfb6911519"
            };

            axios({
                method: "post",
                url: "https://buy.itunes.apple.com/verifyReceipt",
                data: reqBody
            }).then(function (api_response) {
                console.log(JSON.stringify(api_response.data));
                console.log(reqBody);
                var status = api_response.data['status'];

                if (status === 21007) {
                    //Need to call sandbox API
                    axios({
                        method: "post",
                        url: "https://sandbox.itunes.apple.com/verifyReceipt",
                        data: reqBody
                    }).then(function (api_response) {
                        console.log(JSON.stringify(api_response.data));
                        var status = api_response.data['status'];
                        if (status === 0) {
                            var receiptJSON = api_response.data['receipt'];
                            var inApp = receiptJSON['in_app'];
                            var originalTransactionId = inApp[0]['original_transaction_id'];
                            var expires_date_ms = inApp[0]['expires_date_ms'];
                            updateData(
                                pluginId,
                                originalTransactionId,
                                new Date(parseInt(expires_date_ms)),
                                userId,
                                response,
                                userPremiumCollection,
                                productId,
                                purchaseId,
                                platform,
                            );
                        } else {
                            response.send({ status: false, message: "something went wrong please try again" });
                        }
                    }).catch(function (error) {
                        response.send({ status: false, message: "something went wrong please try again" });
                    });
                } else if (status === 0) {
                    var receiptJSON = api_response.data['receipt'];
                    var inApp = receiptJSON['in_app'];
                    var originalTransactionId = inApp[0]['original_transaction_id'];
                    var expires_date_ms = inApp[0]['expires_date_ms'];
                    updateData(
                        pluginId,
                        originalTransactionId,
                        new Date(parseInt(expires_date_ms)),
                        userId,
                        response,
                        userPremiumCollection,
                        productId,
                        purchaseId,
                        platform,
                    );
                } else {
                    response.send({ status: false, message: "something went wrong please try again" });
                }
            }).catch(function (error) {
                response.send({ status: false, message: "something went wrong please try again" });
            });
        } else {
            response.send({ status: false, message: "User not found" });
        }
    });
});

exports.onChangeiOSPurchaseStatus = functions.https.onRequest((request, response) => {
    console.log(request.body);
    onChangeiOSPurchaseState(userPremiumCollection, request, response);
});

exports.onChangeAndroidPurchaseStatus = functions.https.onRequest((request, response) => {
    onChangeAndroidPurchaseState(userPremiumCollection, request, response);
});

// ================================== Functions ==================================

function updateData(
    pluginId,
    transactionId,
    expireDate,
    docId,
    response,
    userCollection,
    productId,
    purchaseId,
    platform,
) {
    console.log("transactionId", transactionId);
    var transId = transactionId.split('..')[0];
    console.log("transId", transId);
    db.collection(userCollection).where("transaction_id", '==', transId).get().then(snapshot => {
        console.log("snapshot", snapshot);
        console.log("docId", docId);
        if (snapshot.empty === true) {
            db.collection(userCollection).add({
                user_id: docId,
                transaction_id: transId,
                product_id: productId,
                purchase_id: purchaseId,
                plugin_id: pluginId,
                platform: platform,
                is_premium: true,
                start_date: new Date().toISOString(),
                expiry_date: expireDate.toISOString(),
            }).then(ref => {
                console.log("Purchase successfully");
                response.send({ status: true, message: "Purchase successful. Thanks! You can manage your subscriptions in your Apple ID account settings." });
            });
        } else {
            console.log("snapshot.docs", snapshot.docs);
            console.log("snapshot.docs[0].id", snapshot.docs[0].id);
            var existDocId = snapshot.docs[0].id;
            if (existDocId === docId) {
                db.collection(userCollection).doc(docId).update({
                    is_premium: true,
                    transaction_id: transId,
                    expiry_date: expireDate.toISOString()
                }).then(ref_1 => {
                    console.log("Purchase restored");
                    response.send({ status: true, message: "Purchase restored successfully. You can manage your subscriptions in your Apple ID account settings." });
                });
            } else {
                console.log("Purchase different email");
                response.send({ status: false, message: "Sorry!, you already subscribed with different email so you can't restore subscription to this account, please login with that email.", transactionId: transId });
            }
        }
    });
}

function onChangeiOSPurchaseState(userCollection, request, response) {
    var notificationType = request.body.notification_type;
    var originalTransactionId = request.body.original_transaction_id;

    db.collection(userCollection).where("transaction_id", '==', originalTransactionId).get().then(snapshot => {
        if (snapshot) {
            snapshot.forEach(doc => {
                var docId = doc.id;
                var isPremium = notAllowedStatus.includes(notificationType) === true ? false : true;
                db.collection(userCollection).doc(docId).update({ is_premium: isPremium }).then(ref => {
                    response.sendStatus(200);
                });
            });
        } else {
            response.sendStatus(200);
        }
    });
}

function onChangeAndroidPurchaseState(userCollection, request, response) {
    var data = request.body.message.data;

    if (data === undefined || data === "" || data === null) {
        response.sendStatus(200);
        return;
    }

    console.log("data", data);

    let buff = new Buffer.from(data, 'base64');
    let text = buff.toString('ascii');
    let json = JSON.parse(text);
    let purchaseToken = json.subscriptionNotification.purchaseToken;
    let subscriptionId = json.subscriptionNotification.subscriptionId;

    var options = {
                        email: 'mailto:revenuecat-subscripton@ai-wearable.iam.gserviceaccount.com',
                        key: '-----BEGIN PRIVATE KEY-----\nMIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQC/Wav+T8Ly69K0\nPJatCLuSdpFL0312kMNFXsyM5rM9NQeYpWP+ufkrRU25RwVVEWf4MwmI8FjyFb/V\nSURlqvqeLxGchbpiTPWqJ2g7U7qt+ncngTo1bQ/9Zd5AkIjUZkGyW8NrsYJl1Oml\n24cy9mJXjRNb9na2gnJllF+GaQPY8G28a5pGMavLwkCiQke+1hx580mleE0ur4lR\nniW/IwRoXTtehVuvt/gjhywRvfpbMUNrG+M37PRYerP7FNl5fGgopdr8jnrFX5zD\nTgHoqr1eYaVIzC0RkNqc6DlWuFw4YNJ7pgnYB4eCzfsPVopemnQAVNROOfSV7Qvp\nIaWJ+bF3AgMBAAECggEAEgciR7L/FID4WIfO0F2ewnVOSh0SWH3aD+qXDf1cTLt2\nzEBk0+Z0ncmJQZf53iJmL8GrN84hKym2aaNeANAjjYy0tZD51vIWQSI2VUSVtXeA\nC2ZG9Cqi04Zp8p5Lbet2bBXuKvLN7Mcq/jfZHImPCV2ewc7OL3LJ0V0xxMmXFbSj\nW9iHJagqRl1PGTUlUmVaRagrIFpm3ctf6lHK5thuXWav6wFvbWg7d5HtLCkp4/fk\nc33fOuI4jr+4UBtf9hDXHE+YosKVdDiHmgweJgwFC2kPh6jIFn1v2wN+KOETsp7I\ng+m7KjoZnKzMY9sxiskMECbOBYwvd0xOqNJWKlLssQKBgQDxzVp0PUH0kit7fEfU\nDztT/gpdsMWJ2D5e78E0rCBbvl7cEaQfVLgZ2Qc3YWrOBA1j6a9j1F5U+Xsx5joF\nNydr6VTQ37pBj1xcDVsYL6/fKm/1YdVnECSyn0a8fS+ToSV1gGqAsWT1pXZrFU7n\ncUEoBIP4RzpFxvYZBQaFNm020QKBgQDKlfObptO7g9I0rWZqK0Ed+dQzRIJefyrW\n2fIed9mf5usPG2cDECfyCNnahfq8Lu6etQIpff2NsHUGvhxlilZDaJpdfw+1/tmH\noFazfCZgmaSnxEoutCNwtxIb4M0GYUV5WmqcfoAUvr9l/byzPixMHtsSiKNj85rN\nxzqIjWIFxwKBgQC/oqShozr2fjH/+AtlQX0foCLPBh5IlR05WIKjIBe1HjdH6qNM\nQXR2584UUhy3kfaazMW4NMNeTSsZ7QDmyUNw/se9ktKmytvECMG9dW3JTHTW4Oak\ne+LZvent0Lk4I2rwqQm/XNhK5wvm6khSnSuqb4m355uDWaAJTDZStUPxQQKBgQCB\nGKuDvfzhWrCClxlTgLrfQkwCW58EXt9KyNospk1NQ5b5KoorfokmCJPjWEuezf2L\nr2dwT3RbbV417MIlxtEP5cGw4P5/CKdQcVGu0OeX2XD+4+wt9Oc8tbzZfRjJ/wSJ\nv59+mHJARgmsEdTFGFKcM3GBTwdn813r0hCv4gDcEwKBgQCsXLMQNZiYR4KIdekG\n1Lk1WUsx6GGIWCsbkOg4lfBGK0oS029S+tFq6mdbDHV3e0HQtpib9wECPfzIdYx5\nrGIGyh+8YwTVNHaoFHl+U84gLOZQW4oGEwU//bQeOQh47Bwh/Of8yUlHtmahZNwl\nvGhsDgl7C9YTf68whbUSytqnGg==\n-----END PRIVATE KEY-----\n'
                    };

    var verifier = new Verifier(options);

    var receiptDic = {
        packageName: "com.ai.wearable",
        productId: subscriptionId,
        purchaseToken: purchaseToken
    };

    verifier.verifySub(receiptDic).then(function (res) {
        var orderId = res.payload.orderId;
        console.log("orderId", orderId);
        orderId = orderId.split('..')[0];
        db.collection(userCollection).where("transaction_id", '==', orderId).get().then(snapshot => {
            if (snapshot) {
                snapshot.forEach(doc => {
                    var docId = doc.id;

                    console.log("doc", doc.data(), doc.data().product_id, doc.data().purchase_id, doc.data().platform);

                    if ((res.payload.paymentState === undefined || res.payload.paymentState === null) || (res.payload.cancelReason != undefined || res.payload.cancelReason >= 0)) {
                        db.collection(userCollection).doc(docId).update({ is_premium: false }).then(ref => {
                            response.sendStatus(200);
                        });
                        return;
                    }

                    if (res.payload.paymentState === 0) {
                        response.sendStatus(200);
                        return;
                    }

                    var transId = res.payload.orderId.split('..')[0];
                    db.collection(userCollection).doc(docId).update({
                        is_premium: true,
                        transaction_id: transId,
                        expiry_date: new Date(parseInt(res.payload.expiryTimeMillis)).toISOString()
                    }).then(ref_1 => {
                        console.log("Purchase restored");
                        response.send({ status: true, message: "Purchase restored successfully. You can manage your subscriptions in your Apple ID account settings." });
                    });

                    updateDataHistory(doc.data().plugin_id,res.payload.orderId, new Date(parseInt(res.payload.expiryTimeMillis)), docId, response, userCollection, doc.data().product_id, doc.data().purchase_id, doc.data().platform, res.payload.purchaseType);
                });
            } else {
                response.sendStatus(200);
            }
        });
    }).then(function (response) {

    }).catch(function (error) {
        console.log("error");
        console.log(error);
        response.sendStatus(200);
    });
}

function updateDataHistory(
    pluginId,
    transactionId,
    expireDate,
    docId,
    response,
    userCollection,
    product_id,
    purchase_id,
    platform,
    purchaseType
) {
    db.collection(userCollection).doc(docId).collection(userHistoryCollection).doc(transactionId).set({
        user_id: docId,
        transaction_id: transactionId,
        product_id: product_id,
        purchase_id: purchase_id,
        platform: platform,
        purchaseType: purchaseType,
        start_date: new Date().toISOString(),
        expiry_date: expireDate.toISOString(),
    }).then(ref => {
        console.log("Purchase successfully");
        response.send({ status: true, message: "Purchase successful. Thanks! You can manage your subscriptions in your Apple ID account settings." });
    });
}

function decodeJWT(token) {
  try {
    if (!token || typeof token !== 'string') {
      throw new Error('Invalid token');
    }

    const parts = token.toString().split('.');
    if (parts.length !== 3) {
      throw new Error('Token does not have three parts');
    }

    const tokenDecodablePart = parts[1];
    const decoded = Buffer.from(tokenDecodablePart, 'base64').toString('utf-8');
    const obj = JSON.parse(decoded);
    return obj;
  } catch (error) {
    console.error('Error decoding token:', error.message);
    return null;
  }
}
