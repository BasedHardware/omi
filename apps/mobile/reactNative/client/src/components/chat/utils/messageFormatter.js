
export const formatBlockMessage = message => {
  const codeblock = /```(\S*)?\s([\s\S]*?)```/g;
  let parts = [];
  let match;
  let lastIndex = 0;

  while ((match = codeblock.exec(message.content)) !== null) {
    let lang = match[1] || 'markdown'; // Default to markdown if no language is specified
    const code = match[2].trim();

    // Adjust language mapping if necessary
    if (lang === 'jsx') {
      lang = 'javascript';
    }

    // Add the text before the code block to the parts array.
    if (match.index > lastIndex) {
      parts.push({
        type: 'text',
        content: message.content.substring(lastIndex, match.index),
      });
    }

    // Add the code block information to the parts array.
    parts.push({
      type: 'code',
      content: code,
      language: lang,
    });

    lastIndex = codeblock.lastIndex;
  }

  // If there's any remaining message content, add it to the parts array.
  if (lastIndex < message.content.length) {
    parts.push({
      type: 'text',
      content: message.content.substring(lastIndex),
    });
  }

  return parts;
};

export const formatStreamMessage = (message, insideCodeBlock, language) => {
  const parts = [];
  if (insideCodeBlock) {
    // Store only the necessary data for rendering the code block later
    parts.push({
      type: 'code',
      content: message.content,
      language: language || 'markdown',
      message_from: message.message_from,
    });
  } else {
    parts.push({
      type: 'text',
      content: message.content,
      message_from: message.message_from,
    });
  }

  return parts;
};
