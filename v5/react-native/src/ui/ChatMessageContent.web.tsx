import React, {useEffect, useRef, useState} from 'react';
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
function textOf(node: React.ReactNode): string {
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node);
  }
  if (Array.isArray(node)) {
    return node.map(textOf).join('');
  }
  if (React.isValidElement(node)) {
    return textOf((node.props as {children?: React.ReactNode}).children);
  }
  return '';
}

/**
 * A fenced code block: a quiet header with the language and a Copy button,
 * and one horizontal scroll for the code (same shape as ChatCodeBlock on
 * native).
 */
function WebCodeBlock({children}: {children?: React.ReactNode}) {
  const child = React.Children.toArray(children)[0];
  const className = React.isValidElement(child)
    ? String((child.props as {className?: string}).className ?? '')
    : '';
  const language = /language-([\w+#-]+)/.exec(className)?.[1];
  const code = textOf(children).replace(/\n$/, '');
  const [copied, setCopied] = useState<'ready' | 'copied' | 'failed'>('ready');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) {
        clearTimeout(timer.current);
      }
    },
    [],
  );
  const label =
    copied === 'copied'
      ? 'Copied'
      : copied === 'failed'
      ? 'Copy unavailable'
      : 'Copy code';
  return (
    <div className="omi-chat-code">
      <div className="omi-chat-code-header">
        <span>{language ?? 'Code'}</span>
        <button
          type="button"
          aria-label={label}
          title={label}
          onClick={() => {
            const clipboard = (
              navigator as Navigator & {
                clipboard?: {writeText(value: string): Promise<void>};
              }
            ).clipboard;
            if (!clipboard) {
              setCopied('failed');
              return;
            }
            clipboard
              .writeText(code)
              .then(() => {
                setCopied('copied');
                if (timer.current !== null) {
                  clearTimeout(timer.current);
                }
                timer.current = setTimeout(() => setCopied('ready'), 1600);
              })
              .catch(() => setCopied('failed'));
          }}>
          {copied === 'copied' ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre>{children}</pre>
    </div>
  );
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
  pre: ({children}) => <WebCodeBlock>{children}</WebCodeBlock>,
  code: ({children, className}) => (
    <code className={className}>{children}</code>
  ),
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
export function ChatMessageContent({
  text,
  style,
  streaming = false,
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
        animated={false}
        isAnimating={false}
        mode={streaming ? 'streaming' : 'static'}>
        {text}
      </Streamdown>
    </div>
  );
}
