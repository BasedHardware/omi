require('dotenv').config();
const Imap = require('imap');
const fs = require('fs');

const imap = new Imap({
  user: process.env.EMAIL_USER,
  password: process.env.EMAIL_PASS,
  host: 'imap.gmail.com',
  port: 993,
  tls: true,
  tlsOptions: {
    rejectUnauthorized: false
  }
});

imap.once('ready', function () {
  imap.openBox('INBOX', false, function (err, box) {
    if (err) throw err;
    imap.search(['UNSEEN', ['SINCE', 'June 20, 2025']], function (err, results) {
      if (err || !results.length) {
        console.log("No new emails found.");
        return imap.end();
      }

      const f = imap.fetch(results, { bodies: '' });
      f.on('message', function (msg) {
        let buffer = '';
        msg.on('body', function (stream) {
          stream.on('data', function (chunk) {
            buffer += chunk.toString('utf8');
          });
        });
        msg.once('end', function () {
          console.log("📥 Email Fetched:\n", buffer);
          fs.appendFileSync('importedNotes.txt', buffer + "\n\n");
        });
      });

      f.once('end', function () {
        console.log("✅ All emails imported.");
        imap.end();
      });
    });
  });
});

imap.once('error', function (err) {
  console.error(err);
});

imap.once('end', function () {
  console.log("Connection closed.");
});

imap.connect();