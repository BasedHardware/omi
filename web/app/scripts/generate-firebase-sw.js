#!/usr/bin/env node

/**
 * Generate firebase-messaging-sw.js from template with environment variables
 * Run this before dev/build to inject Firebase config into the service worker
 */

const fs = require('fs');
const path = require('path');

// Load .env.local if it exists (for local development)
const envLocalPath = path.join(__dirname, '..', '.env.local');
if (fs.existsSync(envLocalPath)) {
  const envContent = fs.readFileSync(envLocalPath, 'utf8');
  envContent.split('\n').forEach((line) => {
    const [key, ...valueParts] = line.split('=');
    if (key && valueParts.length > 0) {
      const value = valueParts.join('=').trim();
      // Remove quotes if present
      process.env[key.trim()] = value.replace(/^["']|["']$/g, '');
    }
  });
}

const templatePath = path.join(__dirname, '..', 'public', 'firebase-messaging-sw.js.template');
const outputPath = path.join(__dirname, '..', 'public', 'firebase-messaging-sw.js');

// Read template
let template;
try {
  template = fs.readFileSync(templatePath, 'utf8');
} catch (error) {
  console.error('Error reading template file:', error.message);
  process.exit(1);
}

// Environment variable mappings
const replacements = {
  __FIREBASE_API_KEY__: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  __FIREBASE_AUTH_DOMAIN__: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  __FIREBASE_PROJECT_ID__: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  __FIREBASE_STORAGE_BUCKET__: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  __FIREBASE_MESSAGING_SENDER_ID__: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  __FIREBASE_APP_ID__: process.env.NEXT_PUBLIC_FIREBASE_APP_ID,
};

// Check for missing environment variables
const missing = Object.entries(replacements)
  .filter(([, value]) => !value)
  .map(([key]) => key);

if (missing.length > 0) {
  console.error('Missing environment variables for Firebase service worker:');
  missing.forEach((key) => {
    const envVar = key.replace(/__/g, '').replace(/_/g, '_');
    console.error(`  - NEXT_PUBLIC_${envVar}`);
  });
  console.error('\nMake sure these are set in .env.local or environment');
  process.exit(1);
}

// Replace placeholders
let output = template;
Object.entries(replacements).forEach(([placeholder, value]) => {
  output = output.replace(new RegExp(placeholder, 'g'), value);
});

// Write output
try {
  fs.writeFileSync(outputPath, output);
  console.log('Generated firebase-messaging-sw.js successfully');
} catch (error) {
  console.error('Error writing output file:', error.message);
  process.exit(1);
}
