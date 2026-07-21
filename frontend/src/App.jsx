import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, Bot, BookOpen, CheckCircle, MessageCircle, Send, ShieldCheck, Sparkles } from 'lucide-react';
import heroMosque from './assets/masjid-agung-sunda-kelapa.jpg';
import imcMaskLogo from './assets/imc-mask-logo.jpg';
import SourceList from './components/SourceList.jsx';
import { sendChatQuestion } from './services/chatApi.js';

const CHAT_HISTORY_KEY = 'imc-mask-public-chat-history';

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

function HomePage({ goToBot }) {
  return (
    <main className="home-page">
      <nav className="site-nav">
        <a className="brand" href="#home" aria-label="IMC-MASK">
          <img src={imcMaskLogo} alt="Logo IMC-MASK" />
          <span>
            <strong>International Muallaf Center</strong>
            <small>Masjid Agung Sunda Kelapa</small>
          </span>
        </a>
        <button className="nav-cta" type="button" onClick={goToBot}>
          <MessageCircle size={18} />
          Tanya Muallaf Bot
        </button>
      </nav>

      <section className="hero" id="home">
        <div className="hero-copy">
          <span className="eyebrow">IMC-MASK</span>
          <h1>Bersama Menuju Islam dengan Ilmu dan Pembinaan</h1>
          <p>
            Website penelitian Muallaf Bot berbasis RAG untuk membantu pertanyaan awal seputar syahadat,
            ibadah dasar, pembinaan, dan layanan IMC-MASK.
          </p>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={goToBot}>
              <MessageCircle size={20} />
              Tanya Muallaf Bot
            </button>
            <a className="secondary-button" href="#alur">
              <BookOpen size={20} />
              Lihat Alur Syahadat
            </a>
          </div>
          <div className="trust-grid" aria-label="Keunggulan layanan">
            <div>
              <ShieldCheck />
              <strong>Terpercaya</strong>
              <span>Dibina oleh Masjid Agung Sunda Kelapa</span>
            </div>
            <div>
              <CheckCircle />
              <strong>Terstruktur</strong>
              <span>Materi pembinaan mualaf bertahap</span>
            </div>
            <div>
              <Sparkles />
              <strong>RAG + LLM</strong>
              <span>Jawaban disertai rujukan dokumen</span>
            </div>
          </div>
        </div>
        <figure className="hero-media">
          <img src={heroMosque} alt="Masjid Agung Sunda Kelapa" />
        </figure>
      </section>

      <section className="content-section" id="alur">
        <div className="section-heading">
          <span className="eyebrow">Layanan IMC-MASK</span>
          <h2>Alur Ikrar Syahadat</h2>
        </div>
        <div className="steps">
          {[
            'Isi formulir dan surat pernyataan',
            'Lengkapi dokumen persyaratan',
            'Serahkan berkas paling lambat H-1',
            'Hadir 1 jam sebelum prosesi',
            'Membawa 2 saksi laki-laki muslim dewasa',
            'Mengikuti pembinaan minimal 4 pertemuan',
            'Sertifikat diberikan setelah pembinaan selesai',
          ].map((step, index) => (
            <article className="step-card" key={step}>
              <span>{index + 1}</span>
              <p>{step}</p>
            </article>
          ))}
        </div>
      </section>

      <button className="floating-bot" type="button" onClick={goToBot}>
        <MessageCircle size={22} />
        Tanya Muallaf Bot
      </button>
    </main>
  );
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

function BotPage({ goHome }) {
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
      <button className="back-button" type="button" onClick={goHome}>
        <ArrowLeft size={18} />
        Kembali ke Beranda
      </button>
      <aside className="question-sidebar">
        <h2>Pertanyaan umum mualaf</h2>
        {suggestedQuestions.map((item) => (
          <button key={item} type="button" onClick={() => submitQuestion(item)} disabled={isThinking}>
            {item}
          </button>
        ))}
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
  const [path, setPath] = useState(() => window.location.pathname);

  function navigate(nextPath) {
    window.history.pushState({}, '', nextPath);
    setPath(nextPath);
  }

  useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname);
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  if (path === '/bot') {
    return <BotPage goHome={() => navigate('/')} />;
  }

  return <HomePage goToBot={() => navigate('/bot')} />;
}
