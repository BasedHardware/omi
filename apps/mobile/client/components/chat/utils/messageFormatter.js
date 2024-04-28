import React from 'react';
import {Text} from 'react-native';
import SyntaxHighlighter from 'react-native-syntax-highlighter';
import { prism } from 'react-syntax-highlighter/styles/prism';

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

    // Create a React component for the highlighted code
    const highlightedCode = (
      <SyntaxHighlighter language={lang} style={prism}>
        {code}
      </SyntaxHighlighter>
    );

    // Add the text before the code block to the parts array.
    if (match.index > lastIndex) {
      parts.push(
        <Text>{message.content.substring(lastIndex, match.index)}</Text>,
      );
    }

    // Add the highlighted code block to the parts array.
    parts.push(highlightedCode);

    lastIndex = codeblock.lastIndex;
  }

  // If there's any remaining message content, add it to the parts array.
  if (lastIndex < message.content.length) {
    parts.push(<Text>{message.content.substring(lastIndex)}</Text>);
  }

  return parts;
};

export const formatStreamMessage = (message, insideCodeBlock, language) => {
  const parts = [];
  if (insideCodeBlock) {
    const highlightedCode = (
      <SyntaxHighlighter language={language || 'markdown'} style={prism}>
        {message.content}
      </SyntaxHighlighter>
    );
    parts.push(highlightedCode);
  } else {
    parts.push(<Text>{message.content}</Text>);
  }

  return parts;
};
