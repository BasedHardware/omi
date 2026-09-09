import React from 'react';
import {StyleSheet} from 'react-native';
import {Streamdown, type Components} from 'streamdown';
import type {ChatMessageContentProps} from './ChatMessageContent.types';
import 'streamdown/styles.css';
import './ChatMessageContent.css';

function safeLink(value: string) {
  try {
    const url = new URL(value);
    return ['https:', 'http:'].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
const components: Components = {
  strong: ({children}) => <strong>{children}</strong>,
  em: ({children}) => <em>{children}</em>,
  del: ({children}) => <del>{children}</del>,
  a: ({href, children}) => {
    const safe = href ? safeLink(href) : undefined;
    return safe ? (
      <a
        href={safe}
        target="_blank"
        rel="noopener noreferrer"
        referrerPolicy="no-referrer">
        {children}
      </a>
    ) : (
      <span>{children}</span>
    );
  },
  img: ({alt}) => <span>{alt || 'Image omitted'}</span>,
  input: ({checked}) => (
    <input
      type="checkbox"
      checked={checked === true}
      disabled
      readOnly
      aria-label={checked ? 'Completed task' : 'Incomplete task'}
    />
  ),
  pre: ({children}) => <pre>{children}</pre>,
  code: ({children}) => <code>{children}</code>,
};
const allowedElements = [
  'p',
  'br',
  'strong',
  'em',
  'del',
  'blockquote',
  'ul',
  'ol',
  'li',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'pre',
  'code',
  'hr',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
  'a',
  'img',
  'input',
];
const animation = {
  animation: 'fadeIn',
  duration: 150,
  sep: 'word',
  stagger: 10,
  maxBacklogMs: 150,
} as const;

export function ChatMessageContent({
  text,
  style,
  streaming = false,
  reduceMotion = false,
}: ChatMessageContentProps) {
  const flattened = StyleSheet.flatten(style);
  return (
    <div
      className="omi-chat-markdown"
      style={{
        color: flattened?.color as string | undefined,
        fontSize: flattened?.fontSize,
        lineHeight:
          flattened?.lineHeight === undefined
            ? undefined
            : `${flattened.lineHeight}px`,
        fontFamily: flattened?.fontFamily,
      }}>
      <Streamdown
        components={components}
        allowedElements={allowedElements}
        skipHtml
        rehypePlugins={[]}
        urlTransform={safeLink}
        controls={false}
        animated={streaming && !reduceMotion ? animation : false}
        isAnimating={streaming}
        mode={streaming ? 'streaming' : 'static'}>
        {text}
      </Streamdown>
    </div>
  );
}
