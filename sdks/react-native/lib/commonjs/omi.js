"use strict";

Object.defineProperty(exports, "__esModule", {
  value: true
});
exports.echo = void 0;
/**
 * Omi SDK for React Native
 */

/**
 * Echo function that returns a greeting with the provided word
 * @param word - The word to echo back
 * @returns A greeting string with the provided word
 */
const echo = word => {
  console.log('Omi SDK: Echo function called');
  return `Hello from Omi SDK! You said: ${word}`;
};
exports.echo = echo;
//# sourceMappingURL=omi.js.map