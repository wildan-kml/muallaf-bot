import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Bot, MessageSquareText, Send } from 'lucide-react';
import SourceList from './components/SourceList.jsx';
import { sendChatQuestion } from './services/chatApi.js';

const CHAT_HISTORY_KEY = 'imc-mask-public-chat-history';
const FEEDBACK_URL = import.meta.env.VITE_FEEDBACK_URL?.trim();

const suggestedQuestions = [
  'Saya ingin masuk Islam, langkah awalnya apa?',
  'Apa makna dua kalimat syahadat?',
  'Bagaimana belajar wudhu dan shalat dari awal?',
  'Apa saja materi pembinaan setelah syahadat?',
];

function nowTime() {
  return new Intl.DateTimeFormat('id-ID', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date());
}

function BotMessage({ message }) {
  const isUser = message.role === 'user';

  return (
    <article className={`chat-row ${isUser ? 'user' : 'bot'}`}>
      {!isUser && (
        <div className="bot-identity">
          <span>Muallaf Bot</span>
          <Bot size={22} />
        </div>
      )}
      <div className="chat-bubble">
        <div className="message-text">
          {message.text.split('\n\n').map((paragraph, index) => (
            <p key={`${message.id}-${index}`}>{paragraph}</p>
          ))}
        </div>
        {!isUser && message.sources?.length > 0 && <SourceList sources={message.sources} />}
        <time>{message.time}</time>
      </div>
    </article>
  );
}

function BotPage() {
  const [messages, setMessages] = useState(() => {
    try {
      const parsed = JSON.parse(localStorage.getItem(CHAT_HISTORY_KEY) || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });
  const [question, setQuestion] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const listRef = useRef(null);

  useEffect(() => {
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(messages));
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (messages.length) return;
    const intro = {
      id: crypto.randomUUID(),
      role: 'bot',
      text: "Assalamu'alaikum, saya Muallaf Bot. Apa yang ingin kamu tanyakan hari ini?",
      time: nowTime(),
      sources: [],
    };
    setMessages([intro]);
  }, []);

  const apiHistory = useMemo(() => messages.filter((item) => item.role === 'user' || item.role === 'bot'), [messages]);

  async function submitQuestion(text = question) {
    const trimmed = text.trim();
    if (!trimmed || isThinking) return;

    const userMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      text: trimmed,
      time: nowTime(),
      sources: [],
    };

    setMessages((current) => [...current, userMessage]);
    setQuestion('');
    setIsThinking(true);

    try {
      const response = await sendChatQuestion(trimmed, apiHistory);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'bot',
          text: response.answer || 'Maaf, jawaban belum tersedia.',
          time: nowTime(),
          sources: response.mode === 'fallback' ? [] : response.sources,
        },
      ]);
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: 'bot',
          text: 'Backend belum aktif. Jalankan FastAPI terlebih dahulu, lalu coba kembali.',
          time: nowTime(),
          sources: [],
        },
      ]);
    } finally {
      setIsThinking(false);
    }
  }

  return (
    <main className="bot-page">
      <aside className="question-sidebar">
        <h2>Pertanyaan umum mualaf</h2>
        {suggestedQuestions.map((item) => (
          <button key={item} type="button" onClick={() => submitQuestion(item)} disabled={isThinking}>
            {item}
          </button>
        ))}
        {FEEDBACK_URL && (
          <a className="feedback-link" href={FEEDBACK_URL} target="_blank" rel="noreferrer">
            <MessageSquareText size={18} />
            Berikan Feedback
          </a>
        )}
      </aside>
      <section className="chat-shell">
        <div className="date-divider">
          <span>Hari ini</span>
        </div>
        <div className="chat-list" ref={listRef}>
          {messages.map((message) => (
            <BotMessage key={message.id} message={message} />
          ))}
          {isThinking && (
            <article className="chat-row bot">
              <div className="bot-identity">
                <span>Muallaf Bot</span>
                <Bot size={22} />
              </div>
              <div className="chat-bubble thinking">
                <span />
                <span />
                <span />
              </div>
            </article>
          )}
        </div>
        <form
          className="chat-form"
          onSubmit={(event) => {
            event.preventDefault();
            submitQuestion();
          }}
        >
          <textarea
            value={question}
            disabled={isThinking}
            placeholder={isThinking ? 'Muallaf Bot sedang berpikir...' : 'Tulis pertanyaan Anda...'}
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                submitQuestion();
              }
            }}
          />
          <button type="submit" disabled={isThinking || !question.trim()} aria-label="Kirim pertanyaan">
            <Send size={24} />
          </button>
        </form>
      </section>
    </main>
  );
}

export default function App() {
  return <BotPage />;
}
