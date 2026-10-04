import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Bot,
  Calendar,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Heart,
  MessageSquareText,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
  UserCheck,
  Users,
  X,
} from 'lucide-react';
import SourceList from './components/SourceList.jsx';
import DocumentViewer from './components/DocumentViewer.jsx';
import { sendChatQuestion, sendFeedback } from './services/chatApi.js';

const CHAT_HISTORY_KEY = 'imc-mask-public-chat-history-v2';
const PENDING_REQUEST_KEY = 'imc-mask-public-pending-request-v1';
const COPYRIGHT_TEXT = '\u00A9 2026 Copyright by Muhammad Wildan Kamil, Afrida Helen, Mira Suryani.';
const MINIMUM_RESPONSE_DELAY_MS = 5000;
const REQUEST_TIMEOUT_MS = 90000;
const CONTROL_TRANSITION_MS = 2000;
const OPENING_PROMPT_DELAY_MS = 3000;
const OPENING_INTRO_DELAY_MS = 5000;
const MODAL_TRANSITION_MS = 240;
const STATUS_MODAL_DURATION_MS = 5000;
const FEEDBACK_COOLDOWN_KEY = 'muallaf-bot-feedback-cooldown-until-v1';
const FEEDBACK_COOLDOWN_MS = 15 * 60 * 1000;

const questionBank = [
  { icon: Heart, text: 'Saya ingin masuk Islam, langkah awalnya apa?' },
  { icon: BookOpen, text: 'Apa makna dua kalimat syahadat?' },
  { icon: Calendar, text: 'Apa saja materi pembinaan setelah syahadat?' },
  { icon: ShieldCheck, text: 'Bagaimana belajar wudu dan salat dari awal?' },
  { icon: Users, text: 'Bagaimana menjaga hubungan dengan keluarga yang belum Muslim?' },
  { icon: UserCheck, text: 'Kapan saya perlu menghubungi pembina IMC-MASK?' },
  { icon: BookOpen, text: 'Apa saja hal dasar yang perlu dipahami calon mualaf?' },
  { icon: ShieldCheck, text: 'Bagaimana membangun kebiasaan ibadah secara bertahap?' },
  { icon: Calendar, text: 'Apa yang perlu disiapkan sebelum ikrar syahadat?' },
  { icon: BookOpen, text: 'Bagaimana belajar Islam jika masih banyak yang belum saya pahami?' },
  { icon: Heart, text: 'Apakah masuk Islam harus langsung menguasai semua ibadah?' },
  { icon: Users, text: 'Bagaimana bersikap kepada orang tua yang berbeda agama?' },
  { icon: UserCheck, text: 'Apa bentuk pendampingan yang tersedia di IMC-MASK?' },
  { icon: Calendar, text: 'Bagaimana alur ikrar syahadat di IMC-MASK?' },
];

function pickRandomQuestions(count) {
  const items = [...questionBank];
  for (let index = items.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [items[index], items[randomIndex]] = [items[randomIndex], items[index]];
  }
  return items.slice(0, count);
}

function nowTime(value = new Date()) {
  return new Intl.DateTimeFormat('id-ID', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(value);
}

function localDateKey(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function dateLabel(dateKey, currentDateKey) {
  if (dateKey === currentDateKey) return 'Hari ini';
  const [year, month, day] = dateKey.split('-').map(Number);
  return new Intl.DateTimeFormat('id-ID', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date(year, month - 1, day));
}

function messageDateKey(message) {
  return message.createdAt ? localDateKey(message.createdAt) : localDateKey();
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, Math.max(0, milliseconds)));
}

function readPendingRequest() {
  try {
    const parsed = JSON.parse(localStorage.getItem(PENDING_REQUEST_KEY) || 'null');
    return parsed?.id && parsed?.question && Number.isFinite(parsed?.startedAt) ? parsed : null;
  } catch {
    localStorage.removeItem(PENDING_REQUEST_KEY);
    return null;
  }
}

function createMessage(role, text, extras = {}) {
  const createdAt = new Date();
  return {
    id: crypto.randomUUID(),
    role,
    text,
    time: nowTime(createdAt),
    createdAt: createdAt.toISOString(),
    sources: [],
    ...extras,
  };
}

function createIntroductionMessage() {
  return createMessage('bot', "Assalamu'alaikum, saya Muallaf Bot. Saya siap membantu informasi awal seputar proses menjadi muslim, syahadat, ibadah dasar, pembinaan mualaf, dan pendampingan IMC-MASK.", {
    variant: 'intro',
  });
}

function createOpeningPrompt(suggestions) {
  return createMessage('bot', 'Apa yang ingin kamu tanyakan hari ini?', {
    variant: 'prompt',
    suggestions,
  });
}

function viewerSourceFromLocation() {
  const params = new URLSearchParams(window.location.search);
  if (params.get('view') !== 'source' || !params.get('file')) return null;
  const pageNumber = Number(params.get('page')) || null;
  return {
    fileName: params.get('file'),
    title: params.get('title') || 'Dokumen rujukan',
    pageNumber,
  };
}

function renderBoldText(text, keyPrefix) {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) => {
    const key = `${keyPrefix}-inline-${index}`;
    return part.startsWith('**') && part.endsWith('**')
      ? <strong key={key}>{part.slice(2, -2)}</strong>
      : <React.Fragment key={key}>{part}</React.Fragment>;
  });
}

function RichTextBlock({ text, blockKey }) {
  const arabicPattern = /([\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff][\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\s،؛؟﴿﴾۝]*[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff])/gu;
  const segments = text.split(arabicPattern).filter((segment) => segment.trim());

  return segments.map((segment, index) => {
    const key = `${blockKey}-segment-${index}`;
    const isArabic = /[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff]/u.test(segment);
    if (isArabic) {
      return <div className="arabic-text" dir="rtl" lang="ar" key={key}>{segment.trim()}</div>;
    }
    return <p key={key}>{renderBoldText(segment.trim(), key)}</p>;
  });
}

function splitNumberedContent(text) {
  const markerPattern = /(^|\s)(\d+)\.\s+(?=\S)/g;
  const candidates = [...text.matchAll(markerPattern)];
  let matches = [];
  let currentRun = [];

  for (const candidate of candidates) {
    const number = Number(candidate[2]);
    const previousNumber = currentRun.length ? Number(currentRun[currentRun.length - 1][2]) : null;
    currentRun = previousNumber !== null && number === previousNumber + 1
      ? [...currentRun, candidate]
      : [candidate];
    if (currentRun.length > matches.length) matches = currentRun;
  }

  if (matches.length < 2) return null;

  const items = matches.map((match, index) => {
    const contentStart = match.index + match[0].length;
    const contentEnd = matches[index + 1]?.index ?? text.length;
    return text.slice(contentStart, contentEnd).trim();
  });

  return {
    preamble: text.slice(0, matches[0].index).trim(),
    start: Number(matches[0][2]),
    items,
  };
}

function StructuredMessage({ text }) {
  const numbered = splitNumberedContent(text);
  if (!numbered) {
    return text.split(/\n{2,}/).filter(Boolean).map((paragraph, index) => (
      <RichTextBlock key={`paragraph-${index}`} text={paragraph} blockKey={`paragraph-${index}`} />
    ));
  }

  return (
    <>
      {numbered.preamble && <RichTextBlock text={numbered.preamble} blockKey="preamble" />}
      <ol className="answer-list" start={numbered.start}>
        {numbered.items.map((item, index) => {
          const parts = item.split(/\s+-\s+(?=\S)/).filter(Boolean);
          return (
            <li key={`answer-item-${index}`}>
              <RichTextBlock text={parts[0]} blockKey={`item-${index}`} />
              {parts.length > 1 && (
                <ul>
                  {parts.slice(1).map((part, partIndex) => (
                    <li key={`answer-item-${index}-part-${partIndex}`}>
                      <RichTextBlock text={part} blockKey={`item-${index}-part-${partIndex}`} />
                    </li>
                  ))}
                </ul>
              )}
            </li>
          );
        })}
      </ol>
    </>
  );
}

function BotMessage({ message, onSuggestion, onIntroduce, onOpenSource, disabled, isEntering = false }) {
  const isUser = message.role === 'user';

  return (
    <article className={`chat-row ${isUser ? 'user' : 'bot'} ${message.variant || ''} ${isEntering ? 'is-entering' : ''}`}>
      {!isUser && (
        <span className="bot-speaker">
          <span className="bot-speaker-name">Muallaf Bot</span>
          <button
            className="bot-avatar"
            type="button"
            onClick={onIntroduce}
            aria-label="Buka pengenalan Muallaf Bot"
            title="Tentang Muallaf Bot"
          >
            <Bot size={22} />
          </button>
        </span>
      )}
      <div className="chat-bubble">
        <div className="message-text">
          <StructuredMessage text={message.text} />
        </div>
        {!isUser && message.suggestions?.length > 0 && (
          <div className="message-suggestions">
            {message.suggestions.map((suggestion) => (
              <button key={suggestion} type="button" disabled={disabled} onClick={() => onSuggestion(suggestion)}>
                {suggestion}
              </button>
            ))}
          </div>
        )}
        {!isUser && message.sources?.length > 0 && (
          <SourceList sources={message.sources} onOpenSource={onOpenSource} />
        )}
        <time>{message.time}</time>
      </div>
    </article>
  );
}

function BotPage() {
  const [sidebarQuestions, setSidebarQuestions] = useState(() => pickRandomQuestions(6));
  const [viewerSource, setViewerSource] = useState(viewerSourceFromLocation);
  const [openingQuestions, setOpeningQuestions] = useState(() => pickRandomQuestions(3).map((item) => item.text));
  const [sidebarOpen, setSidebarOpen] = useState(() => !window.matchMedia('(max-width: 940px)').matches);
  const [messages, setMessages] = useState(() => {
    try {
      const parsed = JSON.parse(localStorage.getItem(CHAT_HISTORY_KEY) || '[]');
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });
  const [question, setQuestion] = useState('');
  const [enteringUserMessageId, setEnteringUserMessageId] = useState(null);
  const [isThinking, setIsThinking] = useState(() => Boolean(readPendingRequest()));
  const [isRefreshingQuestions, setIsRefreshingQuestions] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [showIntroduction, setShowIntroduction] = useState(true);
  const [isIntroductionClosing, setIsIntroductionClosing] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [isFeedbackClosing, setIsFeedbackClosing] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [feedbackForm, setFeedbackForm] = useState({ identity: '', email: '', feedback: '' });
  const [feedbackStatus, setFeedbackStatus] = useState('');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [isOpeningIntroPending, setIsOpeningIntroPending] = useState(() => messages.length === 0);
  const [isOpeningPromptPending, setIsOpeningPromptPending] = useState(() => (
    messages.length === 1 && messages[0]?.variant === 'intro'
  ));
  const [showResetNotice, setShowResetNotice] = useState(false);
  const [isResetNoticeClosing, setIsResetNoticeClosing] = useState(false);
  const [currentDateKey, setCurrentDateKey] = useState(() => localDateKey());
  const listRef = useRef(null);
  const activeRequestControllerRef = useRef(null);
  const resumedRequestRef = useRef(false);
  const requestInFlightRef = useRef(Boolean(readPendingRequest()));
  const feedbackCloseTimerRef = useRef(null);
  const resetNoticeTimerRef = useRef(null);
  const messageEnterTimerRef = useRef(null);

  useEffect(() => {
    const syncViewerWithHistory = () => setViewerSource(viewerSourceFromLocation());
    window.addEventListener('popstate', syncViewerWithHistory);
    return () => window.removeEventListener('popstate', syncViewerWithHistory);
  }, []);

  useEffect(() => {
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(messages));
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    const compactViewport = window.matchMedia('(max-width: 940px)');
    const syncSidebarWithViewport = (event) => setSidebarOpen(!event.matches);
    compactViewport.addEventListener('change', syncSidebarWithViewport);
    return () => compactViewport.removeEventListener('change', syncSidebarWithViewport);
  }, []);

  useEffect(() => {
    if (!isOpeningIntroPending || showIntroduction || showResetNotice) return undefined;
    const timer = window.setTimeout(() => {
      setMessages((current) => (current.length ? current : [createIntroductionMessage()]));
      setIsOpeningIntroPending(false);
      setIsOpeningPromptPending(true);
    }, OPENING_INTRO_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [isOpeningIntroPending, showIntroduction, showResetNotice]);

  useEffect(() => {
    if (!isOpeningPromptPending || showIntroduction) return undefined;
    const timer = window.setTimeout(() => {
      setMessages((current) => {
        const hasConversation = current.some((message) => message.role === 'user' || message.variant === 'prompt');
        return hasConversation ? current : [...current, createOpeningPrompt(openingQuestions)];
      });
      setIsOpeningPromptPending(false);
    }, OPENING_PROMPT_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [isOpeningPromptPending, openingQuestions, showIntroduction]);

  useEffect(() => () => {
    window.clearTimeout(feedbackCloseTimerRef.current);
    window.clearTimeout(resetNoticeTimerRef.current);
    window.clearTimeout(messageEnterTimerRef.current);
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => setCurrentDateKey(localDateKey()), 60000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (resumedRequestRef.current) return;
    resumedRequestRef.current = true;
    const pendingRequest = readPendingRequest();
    if (pendingRequest) performRequest(pendingRequest);
  }, []);

  const apiHistory = useMemo(
    () => messages.filter(
      (item) => (item.role === 'user' || item.role === 'bot') && !['intro', 'prompt'].includes(item.variant),
    ),
    [messages],
  );

  async function submitQuestion(text = question) {
    const trimmed = text.trim();
    if (!trimmed || requestInFlightRef.current || isThinking || isOpeningIntroPending || isOpeningPromptPending || isResetting) return;
    requestInFlightRef.current = true;

    const userMessage = createMessage('user', trimmed);
    const nextMessages = [...messages, userMessage];
    const pendingRequest = {
      id: crypto.randomUUID(),
      question: trimmed,
      history: apiHistory.map(({ role, text: historyText }) => ({ role, text: historyText })),
      startedAt: Date.now(),
    };

    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(nextMessages));
    localStorage.setItem(PENDING_REQUEST_KEY, JSON.stringify(pendingRequest));
    setMessages(nextMessages);
    setEnteringUserMessageId(userMessage.id);
    window.clearTimeout(messageEnterTimerRef.current);
    messageEnterTimerRef.current = window.setTimeout(() => setEnteringUserMessageId(null), 520);
    setQuestion('');
    setIsThinking(true);
    if (window.matchMedia('(max-width: 940px)').matches) setSidebarOpen(false);
    performRequest(pendingRequest);
  }

  async function performRequest(pendingRequest) {
    requestInFlightRef.current = true;
    const controller = new AbortController();
    activeRequestControllerRef.current = controller;
    setIsThinking(true);

    const elapsed = Date.now() - pendingRequest.startedAt;
    const remainingTimeout = Math.max(1, REQUEST_TIMEOUT_MS - elapsed);
    const timeout = window.setTimeout(() => controller.abort(), remainingTimeout);
    try {
      const responsePromise = sendChatQuestion(
        pendingRequest.question,
        pendingRequest.history,
        { signal: controller.signal },
      );
      const minimumDelay = wait(MINIMUM_RESPONSE_DELAY_MS - elapsed);
      const response = await responsePromise;
      await minimumDelay;
      if (readPendingRequest()?.id !== pendingRequest.id) return;

      setMessages((current) => [
        ...current,
        createMessage('bot', response.answer || 'Maaf, jawaban belum tersedia.', {
          sources: response.mode === 'fallback' ? [] : response.sources,
        }),
      ]);
    } catch (error) {
      if (readPendingRequest()?.id !== pendingRequest.id) return;
      const timedOut = error?.name === 'AbortError';
      setMessages((current) => [
        ...current,
        createMessage(
          'bot',
          timedOut
            ? 'Jawaban belum selesai dalam 90 detik. Silakan periksa koneksi atau layanan backend, lalu kirim ulang pertanyaan Anda.'
            : 'Layanan chatbot tidak dapat dihubungi. Periksa koneksi atau backend, lalu coba kembali.',
        ),
      ]);
    } finally {
      window.clearTimeout(timeout);
      if (readPendingRequest()?.id === pendingRequest.id) {
        localStorage.removeItem(PENDING_REQUEST_KEY);
        setIsThinking(false);
        requestInFlightRef.current = false;
      }
      if (activeRequestControllerRef.current === controller) {
        activeRequestControllerRef.current = null;
      }
    }
  }

  function submitSidebarQuestion(text) {
    setSidebarOpen(false);
    submitQuestion(text);
  }

  function openDocumentViewer(source) {
    const nextViewer = {
      fileName: source.file_name,
      title: source.document_title || 'Dokumen rujukan',
      pageNumber: source.page_number || null,
    };
    const params = new URLSearchParams({
      view: 'source',
      file: nextViewer.fileName,
      title: nextViewer.title,
    });
    if (nextViewer.pageNumber) params.set('page', String(nextViewer.pageNumber));
    window.history.pushState({ muallafBotViewer: true }, '', `?${params.toString()}`);
    setViewerSource(nextViewer);
  }

  function closeDocumentViewer() {
    if (window.history.state?.muallafBotViewer) {
      window.history.back();
      return;
    }
    window.history.replaceState({}, '', window.location.pathname);
    setViewerSource(null);
  }

  async function refreshSidebarQuestions() {
    if (isRefreshingQuestions) return;
    setIsRefreshingQuestions(true);
    await wait(CONTROL_TRANSITION_MS);
    setSidebarQuestions(pickRandomQuestions(6));
    setIsRefreshingQuestions(false);
  }

  async function resetConversation() {
    if (isResetting) return;
    setIsResetting(true);
    activeRequestControllerRef.current?.abort();
    const nextOpeningQuestions = pickRandomQuestions(3).map((item) => item.text);
    localStorage.removeItem(CHAT_HISTORY_KEY);
    localStorage.removeItem(PENDING_REQUEST_KEY);
    setOpeningQuestions(nextOpeningQuestions);
    setSidebarQuestions(pickRandomQuestions(6));
    setQuestion('');
    setMessages([]);
    setIsThinking(false);
    setIsOpeningIntroPending(false);
    setIsOpeningPromptPending(false);
    requestInFlightRef.current = false;
    setShowResetNotice(true);
    setIsResetNoticeClosing(false);
    resetNoticeTimerRef.current = window.setTimeout(async () => {
      setIsResetNoticeClosing(true);
      await wait(MODAL_TRANSITION_MS);
      setShowResetNotice(false);
      setIsResetNoticeClosing(false);
      setMessages([createIntroductionMessage()]);
      setIsOpeningPromptPending(true);
      setIsResetting(false);
    }, STATUS_MODAL_DURATION_MS);
  }

  async function submitFeedbackForm(event) {
    event.preventDefault();
    if (!feedbackForm.email.trim() || !feedbackForm.feedback.trim() || isSubmittingFeedback) return;
    const cooldownUntil = Number(localStorage.getItem(FEEDBACK_COOLDOWN_KEY) || 0);
    if (cooldownUntil > Date.now()) {
      const remainingMinutes = Math.max(1, Math.ceil((cooldownUntil - Date.now()) / 60000));
      setFeedbackStatus(`Feedback sudah dikirim. Coba lagi sekitar ${remainingMinutes} menit lagi.`);
      return;
    }
    setIsSubmittingFeedback(true);
    setFeedbackStatus('');
    try {
      const response = await sendFeedback(feedbackForm);
      setFeedbackStatus(response.message || 'Terima kasih. Feedback Anda telah diterima.');
      setFeedbackForm({ identity: '', email: '', feedback: '' });
      localStorage.setItem(FEEDBACK_COOLDOWN_KEY, String(Date.now() + FEEDBACK_COOLDOWN_MS));
      setFeedbackSent(true);
      feedbackCloseTimerRef.current = window.setTimeout(() => closeFeedback(true), STATUS_MODAL_DURATION_MS);
    } catch (error) {
      setFeedbackStatus(error?.message || 'Feedback belum dapat dikirim. Silakan coba kembali.');
    } finally {
      setIsSubmittingFeedback(false);
    }
  }

  async function closeFeedback(force = false) {
    if (isSubmittingFeedback && !force) return;
    window.clearTimeout(feedbackCloseTimerRef.current);
    setIsFeedbackClosing(true);
    await wait(MODAL_TRANSITION_MS);
    setShowFeedback(false);
    setIsFeedbackClosing(false);
    setFeedbackSent(false);
    setFeedbackStatus('');
  }

  async function closeIntroduction() {
    if (isIntroductionClosing) return;
    setIsIntroductionClosing(true);
    await wait(MODAL_TRANSITION_MS);
    setShowIntroduction(false);
    setIsIntroductionClosing(false);
  }

  function openFeedback() {
    setFeedbackSent(false);
    setFeedbackStatus('');
    setShowFeedback(true);
  }

  const conversationBusy = isThinking || isOpeningIntroPending || isOpeningPromptPending || isResetting;

  if (viewerSource) {
    return <DocumentViewer source={viewerSource} onBack={closeDocumentViewer} />;
  }

  return (
    <main className="bot-page">
      <section className={`bot-shell ${sidebarOpen ? 'sidebar-open' : 'sidebar-closed'}`}>
        <button
          className="bot-sidebar-toggle"
          type="button"
          onClick={() => setSidebarOpen((current) => !current)}
          aria-label={sidebarOpen ? 'Tutup daftar pertanyaan' : 'Buka daftar pertanyaan'}
          aria-expanded={sidebarOpen}
        >
          {sidebarOpen ? <ChevronLeft size={21} /> : <ChevronRight size={21} />}
        </button>

        <aside className="question-sidebar" aria-hidden={!sidebarOpen}>
          <div className="sidebar-heading">
            <h2>Pertanyaan umum mualaf</h2>
            <button
              className={`refresh-questions ${isRefreshingQuestions ? 'is-refreshing' : ''}`}
              type="button"
              onClick={refreshSidebarQuestions}
              disabled={isRefreshingQuestions}
              aria-label="Tampilkan pertanyaan lain"
              title="Tampilkan pertanyaan lain"
            >
              <RefreshCw size={19} />
            </button>
          </div>
          <div className="topic-list">
            {sidebarQuestions.map(({ icon: Icon, text }) => (
              <button
                key={text}
                type="button"
                onClick={() => submitSidebarQuestion(text)}
                disabled={conversationBusy || isRefreshingQuestions}
              >
                <Icon size={20} />
                <span>{text}</span>
                <ChevronRight size={17} />
              </button>
            ))}
          </div>
        </aside>

        <section className="chat-shell">
          <div className="chat-list" ref={listRef}>
            {messages.map((message, index) => {
              const messageDay = messageDateKey(message);
              const previousDay = index > 0 ? messageDateKey(messages[index - 1]) : null;
              return (
                <React.Fragment key={message.id}>
                  {messageDay !== previousDay && (
                    <div className="date-divider"><span>{dateLabel(messageDay, currentDateKey)}</span></div>
                  )}
                  <BotMessage
                    message={message}
                    onSuggestion={submitQuestion}
                    onIntroduce={() => setShowIntroduction(true)}
                    onOpenSource={openDocumentViewer}
                    disabled={conversationBusy}
                    isEntering={message.id === enteringUserMessageId}
                  />
                </React.Fragment>
              );
            })}
            {(isThinking || isOpeningPromptPending || (isOpeningIntroPending && !showIntroduction && !showResetNotice)) && (
              <article className="chat-row bot">
                <span className="bot-speaker">
                  <span className="bot-speaker-name">Muallaf Bot</span>
                  <button
                    className="bot-avatar"
                    type="button"
                    onClick={() => setShowIntroduction(true)}
                    aria-label="Buka pengenalan Muallaf Bot"
                    title="Tentang Muallaf Bot"
                  >
                    <Bot size={22} />
                  </button>
                </span>
                <div className="chat-bubble thinking"><span /><span /><span /></div>
              </article>
            )}
          </div>
          <footer className="chat-footer">
            <form
              className="chat-form"
              onSubmit={(event) => {
                event.preventDefault();
                submitQuestion();
              }}
            >
              <textarea
                value={question}
                disabled={conversationBusy}
                placeholder={conversationBusy ? 'Muallaf Bot sedang berpikir...' : 'Tulis pertanyaan Anda...'}
                rows={1}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    submitQuestion();
                  }
                }}
              />
              <button
                type="submit"
                disabled={conversationBusy || !question.trim()}
                aria-label="Kirim pertanyaan"
              >
                <Send size={20} />
              </button>
            </form>
            <div className="chat-meta">
              <button
                className={`reset-chat-button ${isResetting ? 'is-resetting' : ''}`}
                type="button"
                onClick={resetConversation}
                disabled={isResetting}
                aria-label="Hapus chat dan mulai ulang"
                title="Hapus chat dan mulai ulang"
              >
                <Trash2 size={15} />
                <span>{isResetting ? 'Mengulang...' : 'Ulangi chat'}</span>
              </button>
              <p className="copyright">{COPYRIGHT_TEXT}</p>
              <button
                className="feedback-button"
                type="button"
                onClick={openFeedback}
                aria-label="Kirim feedback"
                title="Kirim feedback"
              >
                <MessageSquareText size={15} />
                <span>Kirim Feedback</span>
              </button>
            </div>
          </footer>
        </section>
      </section>
      {showIntroduction && (
        <div
          className={`introduction-backdrop ${isIntroductionClosing ? 'is-closing' : ''}`}
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeIntroduction();
          }}
        >
          <section
            className={`introduction-dialog ${isIntroductionClosing ? 'is-closing' : ''}`}
            role="dialog"
            aria-modal="true"
            aria-labelledby="introduction-title"
          >
            <button
              className="introduction-close"
              type="button"
              onClick={closeIntroduction}
              aria-label="Tutup pengenalan"
            >
              <X size={19} />
            </button>
            <span className="introduction-avatar"><Bot size={30} /></span>
            <h2 id="introduction-title">Muallaf Bot</h2>
            <p>
              Muallaf Bot adalah asisten informasi awal seputar proses menjadi muslim,
              syahadat, ibadah dasar, pembinaan mualaf, dan layanan IMC-MASK.
            </p>
            <p>
              Untuk kondisi pribadi, hukum, atau keselamatan, Muallaf Bot akan mengarahkan
              Anda kepada pendamping atau bantuan yang sesuai.
            </p>
            <button className="introduction-start" type="button" onClick={closeIntroduction}>
              Mulai bertanya
            </button>
          </section>
        </div>
      )}
      {showFeedback && (
        <div
          className={`feedback-backdrop ${isFeedbackClosing ? 'is-closing' : ''}`}
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeFeedback();
          }}
        >
          <section className={`feedback-dialog ${feedbackSent ? 'is-success' : ''} ${isFeedbackClosing ? 'is-closing' : ''}`} role="dialog" aria-modal="true" aria-labelledby="feedback-title">
            <button className="feedback-close" type="button" onClick={() => closeFeedback()} aria-label="Tutup feedback">
              <X size={19} />
            </button>
            {feedbackSent ? (
              <div className="feedback-success" role="status">
                <CircleCheck size={46} />
                <h2 id="feedback-title">Feedback terkirim</h2>
                <p>{feedbackStatus}</p>
              </div>
            ) : (
              <>
                <h2 id="feedback-title">Kirim Feedback</h2>
                <p className="feedback-description">Masukan Anda membantu pengembangan Muallaf Bot.</p>
                <form className="feedback-form" onSubmit={submitFeedbackForm}>
              <label>
                Identitas <span>(opsional)</span>
                <input
                  type="text"
                  maxLength={120}
                  value={feedbackForm.identity}
                  onChange={(event) => setFeedbackForm((current) => ({ ...current, identity: event.target.value }))}
                  placeholder="Nama atau identitas"
                />
              </label>
              <label>
                Email
                <input
                  type="email"
                  required
                  maxLength={160}
                  value={feedbackForm.email}
                  onChange={(event) => setFeedbackForm((current) => ({ ...current, email: event.target.value }))}
                  placeholder="nama@contoh.com"
                />
              </label>
              <label>
                Isi feedback
                <textarea
                  required
                  rows={6}
                  maxLength={5000}
                  value={feedbackForm.feedback}
                  onChange={(event) => setFeedbackForm((current) => ({ ...current, feedback: event.target.value }))}
                  placeholder="Tuliskan pengalaman, masalah, atau saran Anda..."
                />
              </label>
              {feedbackStatus && <p className="feedback-status" role="status">{feedbackStatus}</p>}
              <button type="submit" disabled={isSubmittingFeedback || !feedbackForm.email.trim() || !feedbackForm.feedback.trim()}>
                <Send size={17} />
                {isSubmittingFeedback ? 'Mengirim...' : 'Kirim feedback'}
              </button>
                </form>
              </>
            )}
          </section>
        </div>
      )}
      {showResetNotice && (
        <div className={`status-backdrop ${isResetNoticeClosing ? 'is-closing' : ''}`} role="presentation">
          <section className={`status-dialog ${isResetNoticeClosing ? 'is-closing' : ''}`} role="status" aria-live="polite">
            <span className="introduction-avatar"><Bot size={30} /></span>
            <h2>Chat sudah diperbarui</h2>
            <p>Muallaf Bot akan memulai percakapan baru.</p>
          </section>
        </div>
      )}
    </main>
  );
}

export default function App() {
  return <BotPage />;
}
