import { formatStreamMessage } from './messageFormatter';

const handleIncomingMessageStream = (
    prevMessage,
    id,
    tokenObj,
    insideCodeBlock
) => {
    let language = '';
    // Ignore empty message_content
    if (tokenObj.content === '') {
        return prevMessage;
    }

    if (tokenObj.language) {
        language = tokenObj.language;
    }

    const messagePartsArray = formatStreamMessage(
        tokenObj,
        insideCodeBlock,
        language
    );

    // Start of a debate Stream
    if (!prevMessage[id] || prevMessage[id].length === 0) {
        return {
            ...prevMessage,
            [id]: [messagePartsArray],
        };
    }

    const lastMessageFrom =
        prevMessage[id][prevMessage[id].length - 1].message_from;
    // If this is truthy that means the last message is an object and this is a start of a new stream
    if (lastMessageFrom) {
        return {
            ...prevMessage,
            [id]: [...prevMessage[id], messagePartsArray],
        };
    } else {
        const newPrevMessage = { ...prevMessage };

        const lastMessageIndex = newPrevMessage[id].length - 1;
        let lastMessage = newPrevMessage[id][lastMessageIndex];

        // Check if the last message is of type 'text' and append the new content to it
        // Get the last object in the lastMessage array
        const lastMessageObject = lastMessage[lastMessage.length - 1];
        if (lastMessageObject.type === messagePartsArray[0].type) {
            // If the types match, append the new content to the last object's content
            lastMessageObject.content += messagePartsArray[0].content;
        } else {
            // If the types do not match, add the new result as a new object in the lastMessage array
            lastMessage.push(messagePartsArray[0]);
        }

        // Update the last message in newPrevMessage
        newPrevMessage[id][lastMessageIndex] = lastMessage;

        // Return the updated messages array without spreading it into a new array
        return newPrevMessage;
    }
};

export const processToken = (
    token,
    setInsideCodeBlock,
    insideCodeBlock,
    setMessages,
    id,
    ignoreNextTokenRef,
    languageRef
) => {
    const codeStartIndicator = /```/g;
    const codeEndIndicator = /``/g;
    let messageContent = token.content;
    if (ignoreNextTokenRef.current) {
        if (token.content.trim() !== '`') {
            // This means the token is not a backtick, so it should be the language
            languageRef.current = token.content.trim();
        }

        // Reset the flag after processing the token, regardless of its content
        ignoreNextTokenRef.current = false;
        return;
    }

    // Check if we are not ignoring this token and if there is a language set
    // This is the next tokenObj after we captured the language.
    if (!ignoreNextTokenRef.current && languageRef.current) {
        // Add the language property to the token object
        token.language = languageRef.current;
        //Removes a new line character
        token.content = ' ';
        // Reset languageRef as it has been used for this code block
        languageRef.current = null;
    }

    if (ignoreNextTokenRef.current) {
        ignoreNextTokenRef.current = false;

        return;
    }

    if (codeStartIndicator.test(messageContent)) {
        setInsideCodeBlock((prevInsideCodeBlock) => !prevInsideCodeBlock);

        ignoreNextTokenRef.current = true;

        return;
    }

    if (codeEndIndicator.test(messageContent)) {
        setInsideCodeBlock((prevInsideCodeBlock) => !prevInsideCodeBlock);

        ignoreNextTokenRef.current = true;

        return;
    }

    // If we reach here, it means the token is not a code start or end indicator
    // So, we can add it to the messages
    setMessages((prevMessage) => {
        const newMessageParts = handleIncomingMessageStream(
            prevMessage,
            id,
            token,
            insideCodeBlock
        );
        return newMessageParts;
    });
};
