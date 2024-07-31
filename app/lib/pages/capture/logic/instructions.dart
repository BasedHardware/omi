// Map<int, int> processedSegments = {};
// _doProcessingOfInstructions() async {
//   for (var element in segments) {
//     var hotWords = ['hey friend', 'hey frend', 'hey fren', 'hey bren', 'hey frank'];
//     for (var option in hotWords) {
//       if (element.text.toLowerCase().contains(option)) {
//         debugPrint('Hey Friend detected');
//         var index = element.text.lastIndexOf(option);
//         if (processedSegments.containsKey(element.id) && processedSegments[element.id] == index) continue;

//         var substring = element.text.substring(index + option.length);
//         var words = substring.split(' ');
//         if (words.length >= 5) {
//           debugPrint('Hey Friend detected and 10 words after');
//           String message = await executeGptPrompt('''
//         The following is an instruction the user sent as a voice message by saying "Hey Friend" + instruction.
//         Extract the only the instruction the user is asking in 5 to 10 words.

//         ${element.text.substring(index)}''');
//           debugPrint('Message: $message');

//           MessageProvider().saveMessage(Message(DateTime.now(), message, 'human'));
//           widget.refreshMessages();
//           dynamic ragInfo = await retrieveRAGContext(message);
//           String ragContext = ragInfo[0];
//           List<Memory> memories = ragInfo[1].cast<Memory>();
//           String body = qaStreamedBody(ragContext, await MessageProvider().retrieveMostRecentMessages(limit: 10));
//           var response = await executeGptPrompt(body);
//           var aiMessage = Message(DateTime.now(), response, 'ai');
//           aiMessage.memories.addAll(memories);
//           MessageProvider().saveMessage(aiMessage);
//           widget.refreshMessages();
//           processedSegments[element.id] = index;
//         }
//       }
//     }
//   }
// }
