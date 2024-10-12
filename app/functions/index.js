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
                    email: 'firebase-adminsdk-qzf8v@newagent-68956.iam.gserviceaccount.com',
                    key: '-----BEGIN PRIVATE KEY-----\nMIIEuwIBADANBgkqhkiG9w0BAQEFAASCBKUwggShAgEAAoIBAQDwJ+iLsIp3prXQ\nY01mXVK0PBJ5f6t1bvkE7MKUfyDNdvQzjkbzF+UzOKA2UPj81914SWuLUqMtm8/6\nEEPYFt9hjyP1N2fUkzuyQ8a3+0FL9JbXopy7Ydu3XFTxEon9LEF6q1GrLcrD+iDy\niBtAWIAuSEHEPB7sI7nN6nt+37olB+unPj7keZQ5PFUvxzVOHjJaTYJqPaD8Aqt6\nvNJe8jFqB8Wgp3y8Fk9Mvo7c0CSKDQyTESeYmOnSzeVItp8RmevNH7IpOHy2q0qD\nUMLWL3L9VR/Ra/hS+PG8T2YrQwhwyplU0W2l6LS9GUlNlr5y3B1jr251Y6hbW2pW\nRqjvS9FxAgMBAAECgf9hcdAJ3jhRFHPxelmNj5BfUYCtjAAmRkEEnozVdD/7Hqk3\nwiNHwApgHjnj0Dc3YN+cTy4z+fP8LZzV+oOMyrsY+tu8RB79QkCWtKmNPYXhK/2I\nwZKW9b4RSIWuy7bx42MuQxWAP7RmkLeNsWxdT4uzO95zoXFqn5Rk2SAC+wSswSDD\nx5uXMzNZpbTJ4RFM/PjcmoFZizUDIk9+axcPV64ANYsneKm/ZKWydj0SiXpWjCOb\nXi/i30cEcj2lZeFwjTC+O/Snx6gY/gPobb+hWT+GHxtP4nIGzcjD08SlVoa/RYeO\nL+mlEo9nJ1gJFC2zoviqKY/aXOZc+uP1W37RnEECgYEA+fS9y7erfJ884XYzqyyO\nc1YcwCN1Zkk29syzjjITXRg13ZEtNCzkEQ2nnPEu61+qCAJ/J6sxP4Q1qmpTpMuT\nVhv3lqDAQv9jJepYnYkQhVgLgC3miqj4oiL9xZ9Q4zTMrQuKTH43E3S4AUXGvnTk\nspjLau5aKBMenS2ovU9JMuECgYEA9faAw5dAlwQJyYY6P3HUFGlbSo4hvEE0RIm8\nqPcgKgoB2teufQGoLp7vq+fetj0dwpErTnkejyliTII98b1pxLcyF34H8BUumoYB\n7RapjE3PnfRBVAF+KJ0Mih/cxdVJ8t+xzDxe30OKQvGDsG/KA3cTg1XusVKzFqET\nGReWAJECgYBouVOzwJZGtmjJhb6MHzTnudJ95d1QJ6ixqn4oO27FeFlJJYQs8gnz\n4yawqJQh5YjVpkYkFqOhmwDpD3dP+kMWtsz6/QrQhzPBNPg/uKeFVqgq4hBPVBAn\nzkVIwUEgkISYk9czyUXGDwbw8Y0dSthuw3mmqYp4c9pFvFWQS2G9wQKBgHsdW+6L\nMwVkPBHnYhiHvYRKCCwVYMV+Tc9QsmJQ8ISaZbtI4kooHirX21fMxCmsBc1yJJ8u\n+SDnshBh0OfDy8FvgV9I8mg18hHeqfAmu89C031Y2apW5PMnSTOKJ1PPIyiy16hH\nP6W5hOdlRGl4S0HYxKekx8lyf7n//jM9HxRBAoGBAO+sV18eJggrI7dKtNDLl4mO\nyN7JGjB3VkmSFHZE/EXYp8zna/Hs5qKZhRLqqqdZktOc8M7YeWa8OCc4fiS+TiyJ\n+ydgGam/CrZDSoyZLqcQib1pzAnIDnw2yiYgaGB58hBWofSD1T9ZHVh0zLLakHTT\n9fVaB8dBcM3mOobUdfRp\n-----END PRIVATE KEY-----\n'
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
        email: 'firebase-adminsdk-qzf8v@newagent-68956.iam.gserviceaccount.com',
        key: '-----BEGIN PRIVATE KEY-----\nMIIEuwIBADANBgkqhkiG9w0BAQEFAASCBKUwggShAgEAAoIBAQDwJ+iLsIp3prXQ\nY01mXVK0PBJ5f6t1bvkE7MKUfyDNdvQzjkbzF+UzOKA2UPj81914SWuLUqMtm8/6\nEEPYFt9hjyP1N2fUkzuyQ8a3+0FL9JbXopy7Ydu3XFTxEon9LEF6q1GrLcrD+iDy\niBtAWIAuSEHEPB7sI7nN6nt+37olB+unPj7keZQ5PFUvxzVOHjJaTYJqPaD8Aqt6\nvNJe8jFqB8Wgp3y8Fk9Mvo7c0CSKDQyTESeYmOnSzeVItp8RmevNH7IpOHy2q0qD\nUMLWL3L9VR/Ra/hS+PG8T2YrQwhwyplU0W2l6LS9GUlNlr5y3B1jr251Y6hbW2pW\nRqjvS9FxAgMBAAECgf9hcdAJ3jhRFHPxelmNj5BfUYCtjAAmRkEEnozVdD/7Hqk3\nwiNHwApgHjnj0Dc3YN+cTy4z+fP8LZzV+oOMyrsY+tu8RB79QkCWtKmNPYXhK/2I\nwZKW9b4RSIWuy7bx42MuQxWAP7RmkLeNsWxdT4uzO95zoXFqn5Rk2SAC+wSswSDD\nx5uXMzNZpbTJ4RFM/PjcmoFZizUDIk9+axcPV64ANYsneKm/ZKWydj0SiXpWjCOb\nXi/i30cEcj2lZeFwjTC+O/Snx6gY/gPobb+hWT+GHxtP4nIGzcjD08SlVoa/RYeO\nL+mlEo9nJ1gJFC2zoviqKY/aXOZc+uP1W37RnEECgYEA+fS9y7erfJ884XYzqyyO\nc1YcwCN1Zkk29syzjjITXRg13ZEtNCzkEQ2nnPEu61+qCAJ/J6sxP4Q1qmpTpMuT\nVhv3lqDAQv9jJepYnYkQhVgLgC3miqj4oiL9xZ9Q4zTMrQuKTH43E3S4AUXGvnTk\nspjLau5aKBMenS2ovU9JMuECgYEA9faAw5dAlwQJyYY6P3HUFGlbSo4hvEE0RIm8\nqPcgKgoB2teufQGoLp7vq+fetj0dwpErTnkejyliTII98b1pxLcyF34H8BUumoYB\n7RapjE3PnfRBVAF+KJ0Mih/cxdVJ8t+xzDxe30OKQvGDsG/KA3cTg1XusVKzFqET\nGReWAJECgYBouVOzwJZGtmjJhb6MHzTnudJ95d1QJ6ixqn4oO27FeFlJJYQs8gnz\n4yawqJQh5YjVpkYkFqOhmwDpD3dP+kMWtsz6/QrQhzPBNPg/uKeFVqgq4hBPVBAn\nzkVIwUEgkISYk9czyUXGDwbw8Y0dSthuw3mmqYp4c9pFvFWQS2G9wQKBgHsdW+6L\nMwVkPBHnYhiHvYRKCCwVYMV+Tc9QsmJQ8ISaZbtI4kooHirX21fMxCmsBc1yJJ8u\n+SDnshBh0OfDy8FvgV9I8mg18hHeqfAmu89C031Y2apW5PMnSTOKJ1PPIyiy16hH\nP6W5hOdlRGl4S0HYxKekx8lyf7n//jM9HxRBAoGBAO+sV18eJggrI7dKtNDLl4mO\nyN7JGjB3VkmSFHZE/EXYp8zna/Hs5qKZhRLqqqdZktOc8M7YeWa8OCc4fiS+TiyJ\n+ydgGam/CrZDSoyZLqcQib1pzAnIDnw2yiYgaGB58hBWofSD1T9ZHVh0zLLakHTT\n9fVaB8dBcM3mOobUdfRp\n-----END PRIVATE KEY-----\n'
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
