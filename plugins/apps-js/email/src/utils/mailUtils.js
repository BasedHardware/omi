const { google } = require('googleapis');
const { getGoogleClient } = require('./googleAuth');
const User = require('../models/User');

async function sendEmail(to, subject, text, html, userId) {
  try {
    // Get the user to access their tokens
    const user = await User.findById(userId);
    if (!user) {
      throw new Error('User not found');
    }

    // Get authenticated Gmail client
    const auth = await getGoogleClient(user);
    const gmail = google.gmail({ version: 'v1', auth });

    // Create the email content
    const utf8Subject = `=?utf-8?B?${Buffer.from(subject).toString('base64')}?=`;
    const messageParts = [
      'From: ' + user.email,
      'To: ' + to,
      'Content-Type: text/html; charset=utf-8',
      'MIME-Version: 1.0',
      `Subject: ${utf8Subject}`,
      '',
      html || text.replace(/\n/g, '<br>')
    ];
    const message = messageParts.join('\n');

    // The body needs to be base64url encoded
    const encodedMessage = Buffer.from(message)
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');

    // Send the email
    const res = await gmail.users.messages.send({
      userId: 'me',
      requestBody: {
        raw: encodedMessage
      }
    });

    console.log('Email sent:', res.data.id);
    return res.data;
  } catch (error) {
    console.error('Error sending email:', error);
    throw error;
  }
}

module.exports = {
  sendEmail
}; 