const functions = require("firebase-functions");
const admin = require("firebase-admin");
// To avoid deployment errors, do not call admin.initializeApp() in your code

// example.ts
import fs from "fs/promises";
import { Document, VectorStoreIndex } from "llamaindex";

exports.retrieveMemories = functions.https.onCall((data, context) => {
  const prompt = data.prompt;
  // Write your code below!

  // Load essay from abramov.txt in Node
  const essay = fs.readFile(
    "node_modules/llamaindex/examples/abramov.txt",
    "utf-8",
  );

  // Create Document object with essay
  const document = new Document({ text: essay });

  // Split text and create embeddings. Store them in a VectorStoreIndex
  const index = VectorStoreIndex.fromDocuments([document]);

  // Query the index
  const queryEngine = index.asQueryEngine();
  const response = queryEngine.query("What did the author do in college?");

  // Output response
  console.log(response.toString());

  // Write your code above!
  return response.toString();
});
