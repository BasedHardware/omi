importScripts('https://www.gstatic.com/firebasejs/9.6.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.6.1/firebase-messaging-compat.js');

firebase.initializeApp({
    apiKey: 'AIzaSyC1U6S-hp8x_utpVDHtZwwBDxobhzRZI1w',
    appId: '1:1031333818730:web:e1b83d713c04245cafb513',
    messagingSenderId: '1031333818730',
    projectId: 'based-hardware-dev',
    authDomain: 'based-hardware-dev.firebaseapp.com',
    storageBucket: 'based-hardware-dev.firebasestorage.app',
});

const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
    console.log('Received background message ', payload);
    self.registration.showNotification(payload.notification.title, {
        body: payload.notification.body,
        icon: '/icons/Icon-192'
    });
});
