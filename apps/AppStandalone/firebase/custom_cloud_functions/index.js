const admin = require("firebase-admin/app");
admin.initializeApp();

const checkUserMemory = require("./check_user_memory.js");
exports.checkUserMemory = checkUserMemory.checkUserMemory;
const notifyUsersToStartRecurrentNew = require("./notify_users_to_start_recurrent_new.js");
exports.notifyUsersToStartRecurrentNew =
  notifyUsersToStartRecurrentNew.notifyUsersToStartRecurrentNew;
const retrieveMemories = require("./retrieve_memories.js");
exports.retrieveMemories = retrieveMemories.retrieveMemories;
