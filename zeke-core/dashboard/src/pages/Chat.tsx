import { useState, useRef, useEffect } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { api, type ChatMessage } from '../lib/api';

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    const newUserMsg: ChatMessage = { role: 'user', content: userMessage };
    const updatedHistory = [...messages, newUserMsg];
    setMessages(updatedHistory);
    setLoading(true);

    try {
      const response = await api.chat(userMessage, updatedHistory);
      setMessages((prev) => [...prev, { role: 'assistant', content: response.message }]);
    } catch (err) {
      console.error('Chat error:', err);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Sorry, something went wrong. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] md:h-[calc(100vh-6rem)]">
      <div className="mb-4 md:mb-6">
        <h1 className="text-2xl md:text-3xl font-bold text-white">Chat with Zeke</h1>
        <p className="text-slate-400 mt-1 text-sm md:text-base">Ask about your schedule, tasks, or memories.</p>
      </div>

      <div className="flex-1 bg-slate-900 rounded-xl border border-slate-700 flex flex-col overflow-hidden min-h-0">
        <div className="flex-1 overflow-y-auto p-3 md:p-4 space-y-3 md:space-y-4">
          {messages.length === 0 && (
            <div className="flex items-center justify-center h-full text-slate-500">
              <div className="text-center px-4">
                <p className="text-base md:text-lg">No messages yet</p>
                <p className="text-sm mt-2">Start a conversation with Zeke</p>
              </div>
            </div>
          )}
          
          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[85%] md:max-w-[75%] rounded-2xl px-4 py-2.5 ${
                  message.role === 'user'
                    ? 'bg-blue-600 text-white rounded-br-md'
                    : 'bg-slate-800 text-slate-200 rounded-bl-md'
                }`}
              >
                <p className="whitespace-pre-wrap text-sm md:text-base">{message.content}</p>
              </div>
            </div>
          ))}
          
          {loading && (
            <div className="flex justify-start">
              <div className="bg-slate-800 rounded-2xl rounded-bl-md px-4 py-2.5 text-slate-400">
                <Loader2 className="w-5 h-5 animate-spin" />
              </div>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>

        <form onSubmit={handleSubmit} className="p-3 md:p-4 border-t border-slate-700 bg-slate-900/50">
          <div className="flex gap-2 md:gap-3">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type your message..."
              className="flex-1 bg-slate-800 text-white rounded-full px-4 py-3 border border-slate-600 focus:outline-none focus:border-blue-500 text-base"
              disabled={loading}
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-blue-600 text-white w-12 h-12 rounded-full hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center flex-shrink-0"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
