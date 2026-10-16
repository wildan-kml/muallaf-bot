import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  BookOpen,
  Bot,
  Calendar,
  ChevronLeft,
  ChevronRight,
  CircleCheck,
  Eye,
  EyeOff,
  Heart,
  MessageSquareText,
  LogOut,
  MoreVertical,
  Pencil,
  Plus,
  RefreshCw,
  Send,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserRound,
  Users,
  X,
} from 'lucide-react';
import SourceList from './components/SourceList.jsx';
import DocumentViewer from './components/DocumentViewer.jsx';
import TurnstileVerification from './components/TurnstileVerification.jsx';
import {
  deleteAccount,
  deleteSession,
  getCurrentAccount,
  getHumanVerificationStatus,
  getPrivacyNotice,
  getSecurityConfig,
  getSessionMessages,
  listSessions,
  loginAccount,
  importGuestConversation,
  registerAccount,
  renameSession,
  sendChatQuestion,
  sendFeedback,
  updateAccount,
  verifyHuman,
} from './services/chatApi.js';

const PENDING_REQUEST_KEY = 'imc-mask-public-pending-request-v1';
const AUTH_SESSION_KEY = 'muallaf-bot-auth-v1';
const GUEST_CHAT_KEY = 'muallaf-bot-guest-chat-v1';
const GUEST_SESSION_DURATION_MS = 60 * 60 * 1000;
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
const MINIMUM_PASSWORD_LENGTH = 8;

function routeFromLocation() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/';
  if (path === '/login') return { name: 'login' };
  if (path === '/register') return { name: 'register' };
  if (path === '/account') return { name: 'account' };
  if (path === '/chat') return { name: 'chat', sessionId: null };
  if (path.startsWith('/chat/')) {
    try {
      const sessionId = decodeURIComponent(path.slice('/chat/'.length));
      return sessionId && !sessionId.includes('/')
        ? { name: 'chat', sessionId }
        : { name: 'unknown' };
    } catch {
      return { name: 'unknown' };
    }
  }
  return path === '/' ? { name: 'home' } : { name: 'unknown' };
}

function chatPath(sessionId = null) {
  return sessionId ? `/chat/${encodeURIComponent(sessionId)}` : '/chat';
}

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

function setAuthValidationMessage(event, fieldName, minimumLength = 0, patternMessage = '') {
  const field = event.currentTarget;
  if (field.validity.valueMissing) {
    field.setCustomValidity(`${fieldName} wajib diisi.`);
  } else if (field.validity.tooShort) {
    field.setCustomValidity(`${fieldName} minimal ${minimumLength} karakter.`);
  } else if (field.validity.patternMismatch) {
    field.setCustomValidity(patternMessage || `${fieldName} belum sesuai format.`);
  } else {
    field.setCustomValidity('Periksa kembali isian ini.');
  }
}

function clearValidationMessage(event) {
  event.currentTarget.setCustomValidity('');
}

function PasswordInput({ visibilityLabel = 'kata sandi', ...inputProps }) {
  const [isVisible, setIsVisible] = useState(false);
  const actionLabel = `${isVisible ? 'Sembunyikan' : 'Tampilkan'} ${visibilityLabel}`;

  return (
    <span className="password-input-wrap">
      <input {...inputProps} type={isVisible ? 'text' : 'password'} />
      <button
        className="password-visibility-toggle"
        type="button"
        disabled={inputProps.disabled}
        onClick={() => setIsVisible((current) => !current)}
        aria-label={actionLabel}
        aria-pressed={isVisible}
        title={actionLabel}
      >
        {isVisible ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
    </span>
  );
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

function readGuestMessages(expiresAt) {
  try {
    const stored = JSON.parse(sessionStorage.getItem(GUEST_CHAT_KEY) || 'null');
    if (!stored || stored.expiresAt !== expiresAt || expiresAt <= Date.now()) {
      sessionStorage.removeItem(GUEST_CHAT_KEY);
      return [];
    }
    return Array.isArray(stored.messages) ? stored.messages : [];
  } catch {
    sessionStorage.removeItem(GUEST_CHAT_KEY);
    return [];
  }
}

function fromStoredMessage(message) {
  const createdAt = new Date(message.created_at);
  return {
    id: message.id,
    role: message.role,
    text: message.content,
    time: nowTime(createdAt),
    createdAt: message.created_at,
    sources: Array.isArray(message.metadata?.sources) ? message.metadata.sources : [],
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
  const arabicPattern = /([\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff](?:[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\s،؛؟﴿﴾۝'"“”‘’()[\]{}.,:;!?0-9٠-٩\-–—]*[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff])?[\s،؛؟﴿﴾۝'"“”‘’()[\]{}.,:;!?0-9٠-٩\-–—]*)/gu;
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

function BotPage({ auth, route, onNavigate, onLogout, onAccountUpdated }) {
  const isGuest = auth.mode === 'guest';
  const [sidebarQuestions, setSidebarQuestions] = useState(() => pickRandomQuestions(6));
  const [viewerSource, setViewerSource] = useState(viewerSourceFromLocation);
  const [openingQuestions, setOpeningQuestions] = useState(() => pickRandomQuestions(3).map((item) => item.text));
  const [sidebarOpen, setSidebarOpen] = useState(() => !window.matchMedia('(max-width: 940px)').matches);
  const [messages, setMessages] = useState(() => (isGuest ? readGuestMessages(auth.expiresAt) : []));
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [historyStatus, setHistoryStatus] = useState(isGuest ? '' : 'Memuat riwayat...');
  const [isLoadingConversation, setIsLoadingConversation] = useState(!isGuest);
  const [question, setQuestion] = useState('');
  const [enteringUserMessageId, setEnteringUserMessageId] = useState(null);
  const [isThinking, setIsThinking] = useState(() => Boolean(readPendingRequest()));
  const [isRefreshingQuestions, setIsRefreshingQuestions] = useState(false);
  const [showIntroduction, setShowIntroduction] = useState(true);
  const [isIntroductionClosing, setIsIntroductionClosing] = useState(false);
  const [showFeedback, setShowFeedback] = useState(false);
  const [isFeedbackClosing, setIsFeedbackClosing] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [feedbackForm, setFeedbackForm] = useState({ identity: '', email: '', feedback: '' });
  const [feedbackStatus, setFeedbackStatus] = useState('');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [showAccountSettings, setShowAccountSettings] = useState(false);
  const [accountForm, setAccountForm] = useState({ displayName: auth.user.display_name, currentPassword: '', newPassword: '', confirmPassword: '' });
  const [accountStatus, setAccountStatus] = useState('');
  const [isSavingAccount, setIsSavingAccount] = useState(false);
  const [editingDisplayName, setEditingDisplayName] = useState(false);
  const [editingPassword, setEditingPassword] = useState(false);
  const [showDeleteAccount, setShowDeleteAccount] = useState(false);
  const [deleteAccountUsername, setDeleteAccountUsername] = useState('');
  const [isDeletingAccount, setIsDeletingAccount] = useState(false);
  const [sessionMenuId, setSessionMenuId] = useState(null);
  const [pendingConfirmation, setPendingConfirmation] = useState(null);
  const [renameTarget, setRenameTarget] = useState(null);
  const [renameTitle, setRenameTitle] = useState('');
  const [isOpeningIntroPending, setIsOpeningIntroPending] = useState(() => messages.length === 0);
  const [isOpeningPromptPending, setIsOpeningPromptPending] = useState(() => (
    messages.length === 1 && messages[0]?.variant === 'intro'
  ));
  const [currentDateKey, setCurrentDateKey] = useState(() => localDateKey());
  const listRef = useRef(null);
  const restoreLatestChatRef = useRef(false);
  const activeRequestControllerRef = useRef(null);
  const resumedRequestRef = useRef(false);
  const requestInFlightRef = useRef(Boolean(readPendingRequest()));
  const feedbackCloseTimerRef = useRef(null);
  const messageEnterTimerRef = useRef(null);

  const closeAccountSettings = () => {
    setShowAccountSettings(false);
    if (window.history.state?.muallafAccount) {
      window.history.back();
    } else {
      onNavigate(chatPath(currentSessionId), { replace: true });
    }
  };

  useEffect(() => {
    const syncViewerWithHistory = () => setViewerSource(viewerSourceFromLocation());
    window.addEventListener('popstate', syncViewerWithHistory);
    return () => window.removeEventListener('popstate', syncViewerWithHistory);
  }, []);

  useEffect(() => {
    if (viewerSource || !restoreLatestChatRef.current) return undefined;
    restoreLatestChatRef.current = false;
    const frame = window.requestAnimationFrame(() => {
      listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'auto' });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [viewerSource]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    let active = true;
    async function loadHistory() {
      if (isGuest) {
        if (messages.length) {
          setShowIntroduction(false);
          setIsOpeningIntroPending(false);
          setIsOpeningPromptPending(false);
        }
        setHistoryStatus('');
        setIsLoadingConversation(false);
        return;
      }
      if (route.name === 'account') {
        setIsLoadingConversation(false);
        return;
      }
      setIsLoadingConversation(true);
      try {
        const result = await listSessions(auth.token);
        const nextSessions = result.sessions || [];
        const selected = route.sessionId
          ? nextSessions.find((session) => session.id === route.sessionId && Number(session.message_count) > 0) || null
          : null;
        if (!active) return;
        setSessions(nextSessions);
        setCurrentSessionId(selected?.id || null);
        if (!selected) {
          setMessages(showIntroduction ? [] : [createIntroductionMessage()]);
          setIsOpeningIntroPending(showIntroduction);
          setIsOpeningPromptPending(!showIntroduction);
          setHistoryStatus('');
          setIsLoadingConversation(false);
          if (route.sessionId) onNavigate('/chat', { replace: true });
          return;
        }
        const stored = await getSessionMessages(auth.token, selected.id);
        if (!active) return;
        const restored = (stored.messages || []).map(fromStoredMessage);
        setMessages(restored);
        if (restored.length) {
          setShowIntroduction(false);
          setIsOpeningIntroPending(false);
          setIsOpeningPromptPending(false);
        }
        setHistoryStatus('');
        setIsLoadingConversation(false);
      } catch (error) {
        if (error?.status === 401) onLogout();
        else setHistoryStatus(error?.message || 'Riwayat belum dapat dimuat.');
        if (active) setIsLoadingConversation(false);
      }
    }
    loadHistory();
    return () => { active = false; };
  }, [auth.token, isGuest, route.name, route.sessionId]);

  useEffect(() => {
    if (route.name === 'account' && !isGuest) {
      openAccountSettings(false);
    } else {
      setShowAccountSettings(false);
    }
  }, [route.name, isGuest]);

  useEffect(() => {
    if (!isGuest) return;
    sessionStorage.setItem(GUEST_CHAT_KEY, JSON.stringify({ expiresAt: auth.expiresAt, messages }));
  }, [auth.expiresAt, isGuest, messages]);

  useEffect(() => {
    const compactViewport = window.matchMedia('(max-width: 940px)');
    const syncSidebarWithViewport = (event) => setSidebarOpen(!event.matches);
    compactViewport.addEventListener('change', syncSidebarWithViewport);
    return () => compactViewport.removeEventListener('change', syncSidebarWithViewport);
  }, []);

  useEffect(() => {
    if (!isOpeningIntroPending || showIntroduction) return undefined;
    const timer = window.setTimeout(() => {
      setMessages((current) => (current.length ? current : [createIntroductionMessage()]));
      setIsOpeningIntroPending(false);
      setIsOpeningPromptPending(true);
    }, OPENING_INTRO_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [isOpeningIntroPending, showIntroduction]);

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

  function openSession(sessionId) {
    if (isGuest) return;
    if (!sessionId || sessionId === currentSessionId || conversationBusy) return;
    setSessionMenuId(null);
    setHistoryStatus('Memuat percakapan...');
    setIsLoadingConversation(true);
    onNavigate(chatPath(sessionId));
    if (window.matchMedia('(max-width: 940px)').matches) setSidebarOpen(false);
  }

  async function startNewSession() {
    if (conversationBusy) return;
    onNavigate('/chat');
    if (isGuest) {
      setCurrentSessionId(null);
      setMessages([createIntroductionMessage()]);
      setQuestion('');
      setOpeningQuestions(pickRandomQuestions(3).map((item) => item.text));
      setIsOpeningIntroPending(false);
      setIsOpeningPromptPending(true);
      setHistoryStatus('');
      return;
    }
    setCurrentSessionId(null);
    setMessages([createIntroductionMessage()]);
    setQuestion('');
    setOpeningQuestions(pickRandomQuestions(3).map((item) => item.text));
    setIsOpeningIntroPending(false);
    setIsOpeningPromptPending(true);
    setHistoryStatus('');
  }

  async function deleteCurrentConversation() {
    if (conversationBusy || (isGuest ? !messages.length : !currentSessionId)) return;
    setPendingConfirmation({ type: 'delete-current' });
  }

  async function performDeleteCurrentConversation() {
    if (isGuest) {
      setMessages([createIntroductionMessage()]);
      setQuestion('');
      setIsOpeningIntroPending(false);
      setIsOpeningPromptPending(true);
      return;
    }
    if (!currentSessionId) return;
    setHistoryStatus('Menghapus percakapan...');
    try {
      await deleteSession(auth.token, currentSessionId);
      const result = await listSessions(auth.token);
      const nextSessions = result.sessions || [];
      const selected = nextSessions.find((session) => Number(session.message_count) > 0) || null;
      const stored = selected ? await getSessionMessages(auth.token, selected.id) : { messages: [] };
      const restored = (stored.messages || []).map(fromStoredMessage);
      setSessions(nextSessions);
      setCurrentSessionId(selected?.id || null);
      setMessages(restored.length ? restored : [createIntroductionMessage()]);
      setIsOpeningIntroPending(false);
      setIsOpeningPromptPending(!restored.length);
      setHistoryStatus('');
      onNavigate(chatPath(selected?.id || null), { replace: true });
    } catch (error) {
      setHistoryStatus(error?.message || 'Percakapan belum dapat dihapus.');
    }
  }

  async function submitQuestion(text = question) {
    const trimmed = text.trim();
    if (!trimmed || requestInFlightRef.current || isThinking || isOpeningIntroPending || isOpeningPromptPending) return;
    requestInFlightRef.current = true;

    const userMessage = createMessage('user', trimmed);
    const nextMessages = [...messages, userMessage];
    const pendingRequest = {
      id: crypto.randomUUID(),
      question: trimmed,
      history: apiHistory.map(({ role, text: historyText }) => ({ role, text: historyText })),
      startedAt: Date.now(),
      sessionId: currentSessionId,
    };

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
        {
          signal: controller.signal,
          token: auth.token,
          sessionId: pendingRequest.sessionId || currentSessionId,
        },
      );
      const minimumDelay = wait(MINIMUM_RESPONSE_DELAY_MS - elapsed);
      const response = await responsePromise;
      await minimumDelay;
      if (readPendingRequest()?.id !== pendingRequest.id) return;

      if (response.session_id && response.session_id !== currentSessionId) {
        setCurrentSessionId(response.session_id);
        onNavigate(chatPath(response.session_id), { replace: true });
      }

      setMessages((current) => [
        ...current,
        createMessage('bot', response.answer || 'Maaf, jawaban belum tersedia.', {
          sources: response.mode === 'fallback' ? [] : response.sources,
        }),
      ]);
      if (!isGuest) {
        listSessions(auth.token).then((result) => setSessions(result.sessions || [])).catch(() => {});
      }
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
    restoreLatestChatRef.current = true;
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
    restoreLatestChatRef.current = true;
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

  function openAccountSettings(navigate = true) {
    setAccountForm({ displayName: auth.user.display_name, currentPassword: '', newPassword: '', confirmPassword: '' });
    setAccountStatus('');
    setEditingDisplayName(false);
    setEditingPassword(false);
    setShowDeleteAccount(false);
    setDeleteAccountUsername('');
    setShowAccountSettings(true);
    if (navigate) {
      onNavigate('/account', {
        state: { muallafAccount: true, returnTo: chatPath(currentSessionId) },
      });
    }
  }

  async function submitAccountSettings(event) {
    event.preventDefault();
    if (isSavingAccount) return;
    if (editingPassword && accountForm.newPassword !== accountForm.confirmPassword) {
      setAccountStatus('Konfirmasi kata sandi baru tidak cocok.');
      return;
    }
    if (!editingDisplayName && !editingPassword) {
      setAccountStatus('Pilih Ganti pada nama lengkap atau kata sandi terlebih dahulu.');
      return;
    }
    setIsSavingAccount(true);
    setAccountStatus('');
    try {
      const result = await updateAccount(auth.token, {
        display_name: editingDisplayName ? accountForm.displayName.trim() : null,
        current_password: editingPassword ? accountForm.currentPassword : null,
        new_password: editingPassword ? accountForm.newPassword : null,
        new_password_confirm: editingPassword ? accountForm.confirmPassword : null,
      });
      onAccountUpdated(result.user);
      setAccountForm((current) => ({ ...current, currentPassword: '', newPassword: '', confirmPassword: '' }));
      setEditingDisplayName(false);
      setEditingPassword(false);
      setAccountStatus(result.message || 'Pengaturan akun berhasil diperbarui.');
    } catch (error) {
      setAccountStatus(error?.message || 'Pengaturan akun belum dapat diperbarui.');
    } finally {
      setIsSavingAccount(false);
    }
  }

  async function confirmDeleteAccount(event) {
    event.preventDefault();
    if (deleteAccountUsername.trim().toLowerCase() !== auth.user.username.toLowerCase()) {
      setAccountStatus('Nama pengguna konfirmasi tidak cocok.');
      return;
    }
    setIsDeletingAccount(true);
    setAccountStatus('');
    try {
      await deleteAccount(auth.token, deleteAccountUsername.trim());
      onLogout();
    } catch (error) {
      setAccountStatus(error?.message || 'Akun belum dapat dihapus.');
      setIsDeletingAccount(false);
    }
  }

  async function renameConversation(session) {
    setSessionMenuId(null);
    setRenameTarget(session);
    setRenameTitle(session.title || '');
  }

  async function submitConversationRename(event) {
    event.preventDefault();
    const nextTitle = renameTitle.trim();
    if (!renameTarget || !nextTitle || nextTitle === renameTarget.title) {
      setRenameTarget(null);
      return;
    }
    try {
      const updated = await renameSession(auth.token, renameTarget.id, nextTitle);
      setSessions((current) => current.map((item) => (item.id === renameTarget.id ? { ...item, ...updated } : item)));
      setRenameTarget(null);
    } catch (error) {
      setHistoryStatus(error?.message || 'Judul percakapan belum dapat diubah.');
    }
  }

  async function deleteConversationFromMenu(session) {
    setSessionMenuId(null);
    setPendingConfirmation({ type: 'delete-session', session });
  }

  async function performDeleteConversationFromMenu(session) {
    try {
      await deleteSession(auth.token, session.id);
      const result = await listSessions(auth.token);
      const nextSessions = result.sessions || [];
      setSessions(nextSessions);
      if (session.id === currentSessionId) {
        const selected = nextSessions.find((item) => Number(item.message_count) > 0);
        if (selected) {
          const stored = await getSessionMessages(auth.token, selected.id);
          setCurrentSessionId(selected.id);
          setMessages((stored.messages || []).map(fromStoredMessage));
          setIsOpeningIntroPending(false);
          setIsOpeningPromptPending(false);
          onNavigate(chatPath(selected.id), { replace: true });
        } else {
          setCurrentSessionId(null);
          setMessages([createIntroductionMessage()]);
          setOpeningQuestions(pickRandomQuestions(3).map((item) => item.text));
          setIsOpeningIntroPending(false);
          setIsOpeningPromptPending(true);
          onNavigate('/chat', { replace: true });
        }
      }
    } catch (error) {
      setHistoryStatus(error?.message || 'Percakapan belum dapat dihapus.');
    }
  }

  const conversationBusy = isLoadingConversation || isThinking || isOpeningIntroPending || isOpeningPromptPending;
  const visibleSessions = sessions.filter((session) => Number(session.message_count) > 0 && session.title?.trim());

  function requestLogout() {
    if (isGuest) onLogout();
    else setPendingConfirmation({ type: 'logout' });
  }

  async function confirmPendingAction() {
    const action = pendingConfirmation;
    setPendingConfirmation(null);
    if (action?.type === 'logout') {
      onLogout();
      return;
    }
    if (action?.type === 'delete-current') {
      await performDeleteCurrentConversation();
      return;
    }
    if (action?.type === 'delete-session' && action.session) {
      await performDeleteConversationFromMenu(action.session);
    }
  }

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
          <div className="account-panel">
            {isGuest ? (
              <span className="account-profile-icon" aria-hidden="true"><UserRound size={22} /></span>
            ) : (
              <button
                className="account-profile-icon account-profile-button"
                type="button"
                onClick={openAccountSettings}
                aria-label="Buka pengaturan akun"
                title="Pengaturan akun"
              >
                <UserRound size={22} />
              </button>
            )}
            <div>
              <strong>{auth.user.display_name}</strong>
              <span>{isGuest ? 'Sesi sementara • 1 jam' : `@${auth.user.username}`}</span>
            </div>
            <span className="account-actions">
              <button type="button" onClick={requestLogout} aria-label={isGuest ? 'Masuk atau daftar' : 'Keluar dari akun'} title={isGuest ? 'Masuk atau daftar' : 'Keluar'}>
                <LogOut size={18} />
              </button>
            </span>
          </div>
          <button className="new-session-button" type="button" onClick={startNewSession} disabled={conversationBusy}>
            <Plus size={18} /> Percakapan baru
          </button>
          <div className="session-history" aria-label="Riwayat percakapan">
            <h3>{isGuest ? 'Mode tamu' : 'Riwayat percakapan'}</h3>
            {isGuest ? (
              <p className="guest-session-note">Percakapan hanya tersimpan di tab ini dan dihapus otomatis setelah satu jam.</p>
            ) : (
              <>
                {historyStatus && <p className="history-status">{historyStatus}</p>}
                {visibleSessions.map((session) => (
                  <div className={`session-item ${session.id === currentSessionId ? 'is-active' : ''}`} key={session.id}>
                    <button
                      className="session-open-button"
                      type="button"
                      onClick={() => openSession(session.id)}
                      disabled={conversationBusy}
                      title={session.title}
                    >
                      <MessageSquareText size={16} />
                      <span>{session.title}</span>
                    </button>
                    <button
                      className="session-menu-button"
                      type="button"
                      aria-label={`Kelola percakapan ${session.title}`}
                      aria-expanded={sessionMenuId === session.id}
                      onClick={() => setSessionMenuId((current) => (current === session.id ? null : session.id))}
                    >
                      <MoreVertical size={17} />
                    </button>
                    {sessionMenuId === session.id && (
                      <div className="session-menu" role="menu">
                        <button type="button" role="menuitem" onClick={() => renameConversation(session)}><Pencil size={14} /> Ubah judul</button>
                        <button type="button" role="menuitem" className="is-danger" onClick={() => deleteConversationFromMenu(session)}><Trash2 size={14} /> Hapus</button>
                      </div>
                    )}
                  </div>
                ))}
              </>
            )}
          </div>
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

        <section
          className={`chat-shell ${isLoadingConversation ? 'is-loading-conversation' : ''}`}
          aria-busy={isLoadingConversation}
        >
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
            {(isThinking || isOpeningPromptPending || (isOpeningIntroPending && !showIntroduction)) && (
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
                className={question.trim() ? 'has-value' : ''}
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
              <div className="chat-meta-actions">
                <button
                  className="reset-chat-button delete-conversation-button"
                  type="button"
                  onClick={deleteCurrentConversation}
                  disabled={conversationBusy || (isGuest ? !messages.length : !currentSessionId)}
                  aria-label="Hapus percakapan aktif"
                  title="Hapus percakapan aktif secara permanen"
                >
                  <Trash2 size={15} />
                  <span>Hapus percakapan</span>
                </button>
              </div>
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
          {isLoadingConversation && (
            <div className="conversation-loading-overlay" role="status" aria-live="polite">
              <span className="loading-spinner conversation-loading-spinner" aria-hidden="true" />
              <strong>Memuat percakapan...</strong>
              <span>Mohon tunggu sebentar</span>
            </div>
          )}
        </section>
      </section>
      {showAccountSettings && !isGuest && (
        <div className="account-settings-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) closeAccountSettings(); }}>
          <section className="account-settings-dialog" role="dialog" aria-modal="true" aria-labelledby="account-settings-title">
            <button className="introduction-close" type="button" onClick={closeAccountSettings} aria-label="Tutup pengaturan akun"><X size={19} /></button>
            <span className="privacy-eyebrow">Akun @{auth.user.username}</span>
            <h2 id="account-settings-title">Pengaturan akun</h2>
            <p>Kelola informasi akun dan keamanan Anda.</p>
            <form className="account-settings-form" onSubmit={submitAccountSettings}>
              <div className="account-field-section">
                <div className="account-field-heading"><strong>Nama lengkap</strong><button type="button" onClick={() => setEditingDisplayName((current) => !current)}>{editingDisplayName ? 'Batal' : 'Ganti'}</button></div>
                <input required minLength={2} maxLength={120} disabled={!editingDisplayName} autoComplete="name" value={accountForm.displayName} onChange={(event) => setAccountForm((current) => ({ ...current, displayName: event.target.value }))} />
              </div>
              <div className="account-field-section">
                <div className="account-field-heading"><strong>Nama pengguna</strong></div>
                <input disabled value={auth.user.username} aria-label="Nama pengguna tidak dapat diubah" />
                <small>Nama pengguna tidak dapat diubah.</small>
              </div>
              <div className="account-password-section">
                <div className="account-field-heading"><h3>Kata sandi</h3><button type="button" onClick={() => setEditingPassword((current) => !current)}>{editingPassword ? 'Batal' : 'Ganti'}</button></div>
                {!editingPassword && <p className="masked-password" aria-label="Kata sandi tersimpan">••••••••••</p>}
                {editingPassword && (
                  <>
                    <label>Kata sandi saat ini
                      <PasswordInput required maxLength={128} autoComplete="current-password" placeholder="Masukkan kata sandi saat ini" visibilityLabel="kata sandi saat ini" value={accountForm.currentPassword} onInvalid={(event) => setAuthValidationMessage(event, 'Kata sandi saat ini', 1)} onInput={clearValidationMessage} onChange={(event) => setAccountForm((current) => ({ ...current, currentPassword: event.target.value }))} />
                    </label>
                    <label>Kata sandi baru
                      <PasswordInput required minLength={MINIMUM_PASSWORD_LENGTH} maxLength={128} autoComplete="new-password" placeholder="Minimal 8 karakter" visibilityLabel="kata sandi baru" value={accountForm.newPassword} onInvalid={(event) => setAuthValidationMessage(event, 'Kata sandi baru', MINIMUM_PASSWORD_LENGTH)} onInput={clearValidationMessage} onChange={(event) => setAccountForm((current) => ({ ...current, newPassword: event.target.value }))} />
                      <small className="password-help">Minimal 8 karakter. Boleh menggunakan huruf, angka, atau simbol tanpa syarat kombinasi tertentu.</small>
                    </label>
                    <label>Konfirmasi kata sandi baru
                      <PasswordInput required minLength={MINIMUM_PASSWORD_LENGTH} maxLength={128} autoComplete="new-password" placeholder="Ulangi kata sandi baru" visibilityLabel="konfirmasi kata sandi baru" value={accountForm.confirmPassword} onInvalid={(event) => setAuthValidationMessage(event, 'Konfirmasi kata sandi baru', MINIMUM_PASSWORD_LENGTH)} onInput={clearValidationMessage} onChange={(event) => setAccountForm((current) => ({ ...current, confirmPassword: event.target.value }))} />
                    </label>
                  </>
                )}
              </div>
              {accountStatus && <p className="account-settings-status" role="status">{accountStatus}</p>}
              <button className="introduction-start" type="submit" disabled={isSavingAccount}>{isSavingAccount ? 'Menyimpan...' : 'Simpan perubahan'}</button>
            </form>
            <div className="delete-account-zone">
              <div><strong>Hapus akun</strong><p>Seluruh riwayat percakapan akun akan dihapus permanen.</p></div>
              <button type="button" onClick={() => { setAccountStatus(''); setShowDeleteAccount(true); }}>Hapus akun</button>
            </div>
          </section>
        </div>
      )}
      {showDeleteAccount && !isGuest && (
        <div className="account-settings-backdrop delete-account-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setShowDeleteAccount(false); }}>
          <section className="delete-account-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-account-title">
            <button className="introduction-close" type="button" onClick={() => setShowDeleteAccount(false)} aria-label="Batal menghapus akun"><X size={19} /></button>
            <span className="privacy-eyebrow">Tindakan permanen</span>
            <h2 id="delete-account-title">Hapus akun?</h2>
            <p>Ketik nama pengguna <strong>{auth.user.username}</strong> untuk mengonfirmasi penghapusan akun beserta seluruh riwayat percakapan.</p>
            <form onSubmit={confirmDeleteAccount}>
              <label>Konfirmasi nama pengguna
                <input required autoComplete="off" value={deleteAccountUsername} onChange={(event) => setDeleteAccountUsername(event.target.value)} placeholder={auth.user.username} />
              </label>
              {accountStatus && <p className="account-settings-status" role="alert">{accountStatus}</p>}
              <div className="delete-account-actions">
                <button type="button" onClick={() => setShowDeleteAccount(false)}>Batal</button>
                <button type="submit" className="danger-button" disabled={isDeletingAccount}>{isDeletingAccount ? 'Menghapus...' : 'Hapus permanen'}</button>
              </div>
            </form>
          </section>
        </div>
      )}
      {renameTarget && (
        <div className="custom-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setRenameTarget(null); }}>
          <section className="custom-dialog" role="dialog" aria-modal="true" aria-labelledby="rename-conversation-title">
            <button className="introduction-close" type="button" onClick={() => setRenameTarget(null)} aria-label="Tutup"><X size={19} /></button>
            <span className="custom-dialog-icon"><Pencil size={22} /></span>
            <h2 id="rename-conversation-title">Ubah judul percakapan</h2>
            <p>Gunakan judul singkat yang mudah dikenali di riwayat percakapan.</p>
            <form onSubmit={submitConversationRename}>
              <label>Judul percakapan
                <input required maxLength={160} autoFocus value={renameTitle} onChange={(event) => setRenameTitle(event.target.value)} />
              </label>
              <div className="custom-dialog-actions">
                <button type="button" onClick={() => setRenameTarget(null)}>Batal</button>
                <button type="submit" className="primary">Simpan judul</button>
              </div>
            </form>
          </section>
        </div>
      )}
      {pendingConfirmation && (
        <div className="custom-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPendingConfirmation(null); }}>
          <section className="custom-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmation-title">
            <button className="introduction-close" type="button" onClick={() => setPendingConfirmation(null)} aria-label="Batal"><X size={19} /></button>
            <span className={`custom-dialog-icon ${pendingConfirmation.type.startsWith('delete') ? 'is-danger' : ''}`}>
              {pendingConfirmation.type === 'logout' ? <LogOut size={22} /> : <Trash2 size={22} />}
            </span>
            <h2 id="confirmation-title">{pendingConfirmation.type === 'logout' ? 'Keluar dari akun?' : 'Hapus percakapan?'}</h2>
            <p>
              {pendingConfirmation.type === 'logout'
                ? 'Anda perlu masuk kembali untuk mengakses riwayat percakapan akun.'
                : `Percakapan${pendingConfirmation.session?.title ? ` “${pendingConfirmation.session.title}”` : ''} akan dihapus permanen dan tidak dapat dipulihkan.`}
            </p>
            <div className="custom-dialog-actions">
              <button type="button" onClick={() => setPendingConfirmation(null)}>Batal</button>
              <button type="button" className={pendingConfirmation.type.startsWith('delete') ? 'danger' : 'primary'} onClick={confirmPendingAction}>
                {pendingConfirmation.type === 'logout' ? 'Ya, keluar' : 'Ya, hapus'}
              </button>
            </div>
          </section>
        </div>
      )}
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
    </main>
  );
}

function AuthScreen({ mode, onModeChange, onAuthenticated, onContinueAsGuest }) {
  const [form, setForm] = useState({ username: '', displayName: '', password: '', privacyAccepted: false });
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const [privacy, setPrivacy] = useState(null);
  const [security, setSecurity] = useState({ ready: false, enabled: false, siteKey: null });
  const [humanVerified, setHumanVerified] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([getSecurityConfig(), getHumanVerificationStatus()])
      .then(([config, verification]) => {
        if (!active) return;
        const enabled = Boolean(config?.enabled && config?.site_key);
        setSecurity({ ready: true, enabled, siteKey: config?.site_key || null });
        setHumanVerified(!enabled || Boolean(verification?.verified));
      })
      .catch(() => {
        if (!active) return;
        if (import.meta.env.DEV) {
          setSecurity({ ready: true, enabled: false, siteKey: null });
          setHumanVerified(true);
        } else {
          setSecurity({ ready: true, enabled: true, siteKey: null });
          setHumanVerified(false);
          setStatus('Konfigurasi keamanan belum dapat dimuat. Silakan muat ulang halaman.');
        }
      });
    return () => { active = false; };
  }, []);

  const handleTurnstileToken = React.useCallback(async (token) => {
    setStatus('Memeriksa keamanan...');
    try {
      await verifyHuman(token);
      setHumanVerified(true);
      setStatus('');
    } catch (error) {
      setHumanVerified(false);
      setStatus(error?.message || 'Verifikasi keamanan gagal. Silakan coba kembali.');
    }
  }, []);

  const handleTurnstileError = React.useCallback((message) => {
    setHumanVerified(false);
    setStatus(message);
  }, []);

  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (mode === 'register' && security.enabled && !humanVerified) {
      setStatus('Selesaikan verifikasi keamanan sebelum membuat akun.');
      return;
    }
    setBusy(true);
    setStatus('');
    try {
      if (mode === 'login') {
        const result = await loginAccount(form.username.trim(), form.password);
        await onAuthenticated({ token: result.access_token, user: result.user });
      } else {
        await registerAccount(form);
        setForm((current) => ({
          username: current.username.trim(),
          displayName: '',
          password: '',
          privacyAccepted: false,
        }));
        onModeChange('login', { replace: true });
        setStatus('Akun berhasil dibuat. Silakan masuk dengan nama pengguna dan kata sandi Anda.');
      }
    } catch (error) {
      setStatus(
        mode === 'login' && error?.status === 401
          ? 'Nama lengkap/nama pengguna atau kata sandi salah.'
          : error?.message || 'Akun belum dapat diproses.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function showPrivacy() {
    try {
      setPrivacy(await getPrivacyNotice());
    } catch {
      setPrivacy({
        summary: 'Riwayat percakapan disimpan agar sesi dapat dipulihkan dan dihapus otomatis sesuai masa retensi.',
        retention_days: 30,
        warning: 'Jangan kirimkan informasi pribadi yang tidak diperlukan.',
      });
    }
  }

  return (
    <main className="auth-page">
      <section className={`auth-card ${busy ? 'is-busy' : ''}`} aria-busy={busy || !security.ready}>
        <img className="auth-logo" src="/imc-mask-logo.jpg" alt="Logo International Muallaf Center Masjid Agung Sunda Kelapa" />
        <h1>Muallaf Bot</h1>
        <div className={`auth-tabs is-${mode}`} role="tablist">
          <button type="button" disabled={busy} className={mode === 'login' ? 'is-active' : ''} onClick={() => { onModeChange('login'); setStatus(''); }}>Masuk</button>
          <button type="button" disabled={busy} className={mode === 'register' ? 'is-active' : ''} onClick={() => { onModeChange('register'); setStatus(''); }}>Daftar</button>
        </div>
        <form key={mode} className={`auth-form is-${mode}`} onSubmit={submit}>
          {mode === 'register' && (
            <label>Nama lengkap
              <input disabled={busy} required minLength={2} maxLength={120} autoComplete="name" placeholder="Contoh: Muhammad Wildan" value={form.displayName} onInvalid={(event) => setAuthValidationMessage(event, 'Nama lengkap', 2)} onInput={clearValidationMessage} onChange={(event) => setForm((current) => ({ ...current, displayName: event.target.value }))} />
            </label>
          )}
          <label>{mode === 'login' ? 'Nama lengkap atau nama pengguna' : 'Nama pengguna'}
            <input disabled={busy} required minLength={mode === 'login' ? 1 : 3} maxLength={mode === 'login' ? 120 : 100} autoComplete="username" pattern={mode === 'login' ? undefined : '[a-zA-Z0-9_.-]+'} placeholder={mode === 'login' ? 'Masukkan nama lengkap atau nama pengguna' : 'Contoh: wildan_kamil'} value={form.username} onInvalid={(event) => setAuthValidationMessage(event, mode === 'login' ? 'Nama lengkap atau nama pengguna' : 'Nama pengguna', mode === 'login' ? 1 : 3, 'Nama pengguna hanya boleh berisi huruf, angka, titik, garis bawah, atau tanda hubung.')} onInput={clearValidationMessage} onChange={(event) => setForm((current) => ({ ...current, username: event.target.value }))} />
          </label>
          <label>Kata sandi
            <PasswordInput disabled={busy} required minLength={mode === 'register' ? MINIMUM_PASSWORD_LENGTH : 1} maxLength={128} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} placeholder={mode === 'login' ? 'Masukkan kata sandi' : 'Minimal 8 karakter'} value={form.password} onInvalid={(event) => setAuthValidationMessage(event, 'Kata sandi', mode === 'register' ? MINIMUM_PASSWORD_LENGTH : 1)} onInput={clearValidationMessage} onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))} />
            {mode === 'register' && <small className="password-help">Minimal 8 karakter. Boleh menggunakan huruf, angka, atau simbol tanpa syarat kombinasi tertentu.</small>}
          </label>
          {mode === 'register' && (
            <label className="privacy-consent">
              <input disabled={busy} required type="checkbox" checked={form.privacyAccepted} onInvalid={(event) => event.currentTarget.setCustomValidity('Centang persetujuan ketentuan privasi untuk melanjutkan.')} onInput={clearValidationMessage} onChange={(event) => { clearValidationMessage(event); setForm((current) => ({ ...current, privacyAccepted: event.target.checked })); }} />
              <span>Saya telah membaca dan menyetujui <button type="button" disabled={busy} onClick={showPrivacy}>ketentuan privasi</button>.</span>
            </label>
          )}
          {mode === 'register' && security.enabled && !humanVerified && (
            <TurnstileVerification siteKey={security.siteKey} onToken={handleTurnstileToken} onError={handleTurnstileError} />
          )}
          {status && (
            <p
              className={`auth-status ${status.startsWith('Akun berhasil dibuat') ? 'is-success' : ''}`}
              role={status.startsWith('Akun berhasil dibuat') ? 'status' : 'alert'}
            >
              {status}
            </p>
          )}
          <button className="auth-submit" type="submit" disabled={busy || !security.ready || (mode === 'register' && security.enabled && !humanVerified)}>
            {(busy || !security.ready) && <span className="loading-spinner auth-loading-spinner" aria-hidden="true" />}
            <span>
              {!security.ready
                ? 'Menyiapkan keamanan...'
                : busy
                  ? mode === 'login' ? 'Sedang masuk...' : 'Membuat akun...'
                  : mode === 'login' ? 'Masuk' : 'Buat akun'}
            </span>
          </button>
        </form>
        <div className="guest-access">
          <span>atau</span>
          {mode === 'login' && security.enabled && !humanVerified && (
            <TurnstileVerification siteKey={security.siteKey} onToken={handleTurnstileToken} onError={handleTurnstileError} />
          )}
          <button type="button" disabled={busy || !security.ready || (security.enabled && !humanVerified)} onClick={onContinueAsGuest}>Lanjut sebagai tamu</button>
        </div>
      </section>
      {privacy && (
        <div className="privacy-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPrivacy(null); }}>
          <section className="privacy-dialog" role="dialog" aria-modal="true" aria-labelledby="privacy-title">
            <button className="introduction-close" type="button" onClick={() => setPrivacy(null)} aria-label="Tutup"><X size={19} /></button>
            <header className="privacy-heading">
              <span className="privacy-eyebrow">Pemberitahuan sebelum pendaftaran</span>
              <h2 id="privacy-title">Ketentuan Privasi dan Pengelolaan Data Muallaf Bot</h2>
              <p>
                Ketentuan ini menjelaskan bagaimana data pengguna dikelola dalam Muallaf Bot, sebuah sistem pendamping informasi awal bagi calon mualaf dan mualaf yang dikembangkan dalam konteks penelitian. Bacalah seluruh bagian sebelum membuat akun.
              </p>
            </header>

            <div className="privacy-content">
              <section>
                <h3>1. Ruang lingkup dan tujuan layanan</h3>
                <p>
                  Muallaf Bot menggunakan pendekatan <strong>Retrieval-Augmented Generation (RAG)</strong> untuk mencari informasi dari dokumen rujukan yang telah disiapkan. Layanan ini bertujuan membantu pengguna memperoleh penjelasan awal, menjaga kesinambungan percakapan, dan memudahkan pengguna kembali ke sesi sebelumnya.
                </p>
                <p>
                  Jawaban chatbot bersifat <strong>informasi dan pendampingan awal</strong>. Jawaban tidak menggantikan bimbingan langsung dari pembina mualaf, ustaz, konselor, tenaga kesehatan, atau pihak berwenang ketika persoalan memerlukan penanganan khusus.
                </p>
              </section>

              <section>
                <h3>2. Data yang dikumpulkan</h3>
                <p>Ketika pengguna mendaftar dan menggunakan layanan, sistem dapat menyimpan:</p>
                <ul>
                  <li><strong>Data akun</strong>, yaitu nama lengkap, nama pengguna, dan kata sandi yang telah diubah menjadi hash kriptografis.</li>
                  <li><strong>Data percakapan</strong>, yaitu judul sesi, pertanyaan, jawaban chatbot, sumber rujukan, serta waktu aktivitas.</li>
                  <li><strong>Data persetujuan</strong>, yaitu catatan bahwa pengguna telah menyetujui ketentuan privasi saat pendaftaran.</li>
                  <li><strong>Data teknis keamanan sementara</strong>, seperti alamat jaringan, token Turnstile, dan cookie keamanan satu jam yang diproses untuk membatasi spam, serangan otomatis, dan penggunaan layanan secara berlebihan.</li>
                  <li><strong>Data umpan balik opsional</strong>, termasuk identitas atau alamat surel hanya apabila pengguna memilih untuk mengisinya.</li>
                </ul>
                <p>
                  Pendaftaran akun menggunakan <strong>nama pengguna dan tidak memerlukan alamat email atau kode verifikasi</strong>. Sistem juga tidak meminta nomor identitas, data pembayaran, atau kata sandi layanan lain. Pengguna diminta untuk tidak memasukkan data pribadi sensitif yang tidak diperlukan ke dalam percakapan.
                </p>
              </section>

              <section>
                <h3>3. Tujuan penggunaan data</h3>
                <ul>
                  <li>Membuat dan mengautentikasi akun pengguna secara aman.</li>
                  <li>Menyimpan sesi agar percakapan dapat dilanjutkan tanpa mengulangi pertanyaan dari awal.</li>
                  <li>Menghasilkan jawaban berbasis dokumen dan menampilkan sumber yang relevan.</li>
                  <li>Menjaga keamanan, mengevaluasi kinerja sistem, serta memperbaiki kualitas layanan dan penelitian.</li>
                </ul>
              </section>

              <section>
                <h3>4. Pemrosesan oleh sistem kecerdasan buatan</h3>
                <p>
                  Pertanyaan diproses melalui pencarian basis pengetahuan dan dapat diteruskan kepada <strong>penyedia model kecerdasan buatan yang dikonfigurasi</strong> untuk menyusun jawaban. Jika model tersebut tidak tersedia, sistem menggunakan jawaban ekstraktif dari dokumen. Karena teknologi AI dapat menghasilkan kekeliruan, pengguna tetap dianjurkan memeriksa sumber dan berkonsultasi dengan pembina untuk keputusan penting.
                </p>
              </section>

              <section>
                <h3>5. Penyimpanan, keamanan, dan masa retensi</h3>
                <p>
                  Data akun dan percakapan disimpan pada basis data aplikasi dengan pengendalian akses. Kata sandi <strong>tidak disimpan dalam bentuk teks asli</strong>, sedangkan akses ke histori memerlukan autentikasi akun.
                </p>
                <p>
                  Riwayat percakapan memiliki masa retensi <strong>{privacy.retention_days || 30} hari sejak aktivitas terakhir</strong>. Data yang telah melewati masa tersebut memenuhi syarat untuk dihapus dalam proses pemeriksaan berkala. Pengguna juga dapat menghapus sesi percakapan lebih awal melalui kontrol yang tersedia pada aplikasi.
                </p>
                <p>
                  Pada <strong>mode tamu</strong>, isi percakapan tidak langsung dibuatkan sesi di basis data aplikasi. Salinan sementara hanya disimpan pada tab browser yang digunakan dan kedaluwarsa setelah satu jam. Apabila pengguna kemudian masuk ke akun dalam tab yang sama, percakapan tersebut dipindahkan ke riwayat akun agar dapat dilanjutkan.
                </p>
                <p>
                  Layanan melibatkan <strong>Cloudflare</strong> untuk hosting, rate limit, dan verifikasi Turnstile; <strong>Modal</strong> untuk menjalankan API; <strong>Neon</strong> untuk basis data; serta penyedia model bahasa yang dikonfigurasi. Akses antarlayanan dilindungi dengan kredensial rahasia dan dibatasi untuk kebutuhan operasional.
                </p>
              </section>

              <section>
                <h3>6. Kendali dan hak pengguna</h3>
                <ul>
                  <li>Melihat kembali sesi dan riwayat percakapan miliknya.</li>
                  <li>Mengubah judul atau menghapus percakapan yang tidak lagi ingin disimpan.</li>
                  <li>Mengubah nama lengkap, mengganti kata sandi, atau menghapus akun beserta seluruh riwayatnya.</li>
                  <li>Keluar dari akun untuk mengakhiri sesi pada perangkat yang digunakan.</li>
                  <li>Menyampaikan permintaan koreksi atau penghapusan data melalui saluran umpan balik kepada pengelola.</li>
                </ul>
              </section>

              <section>
                <h3>7. Tanggung jawab dan persetujuan pengguna</h3>
                <p>
                  Pengguna bertanggung jawab menjaga kerahasiaan kata sandi serta memastikan informasi yang dikirim memang diperlukan. Dengan mencentang kotak persetujuan dan membuat akun, pengguna menyatakan telah membaca, memahami, dan menyetujui pemrosesan data sebagaimana dijelaskan dalam ketentuan ini.
                </p>
                <p className="privacy-warning">
                  <strong>Penting:</strong> jangan mengirimkan kata sandi, nomor identitas, informasi pembayaran, rekam medis, atau data pribadi pihak lain melalui percakapan chatbot.
                </p>
              </section>
            </div>

            <div className="privacy-actions">
              <button className="introduction-start" type="button" onClick={() => setPrivacy(null)}>Saya sudah membaca</button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

export default function App() {
  const [route, setRoute] = useState(routeFromLocation);
  const [auth, setAuth] = useState(() => {
    try {
      const stored = JSON.parse(sessionStorage.getItem(AUTH_SESSION_KEY) || 'null');
      if (stored?.mode === 'guest' && stored.expiresAt <= Date.now()) {
        sessionStorage.removeItem(AUTH_SESSION_KEY);
        sessionStorage.removeItem(GUEST_CHAT_KEY);
        return null;
      }
      return stored;
    } catch {
      return null;
    }
  });

  function navigate(path, { replace = false, state = {} } = {}) {
    const current = `${window.location.pathname}${window.location.search}`;
    if (current !== path) {
      window.history[replace ? 'replaceState' : 'pushState'](state, '', path);
    }
    setRoute(routeFromLocation());
  }

  useEffect(() => {
    const syncRoute = () => setRoute(routeFromLocation());
    window.addEventListener('popstate', syncRoute);
    return () => window.removeEventListener('popstate', syncRoute);
  }, []);

  useEffect(() => {
    if (!auth && !['login', 'register'].includes(route.name)) {
      navigate('/login', { replace: true });
      return;
    }
    if (auth && ['home', 'login', 'register', 'unknown'].includes(route.name)) {
      navigate('/chat', { replace: true });
      return;
    }
    if (auth?.mode === 'guest' && route.name === 'account') {
      navigate('/chat', { replace: true });
      return;
    }
    if (auth?.mode === 'guest' && route.name === 'chat' && route.sessionId) {
      navigate('/chat', { replace: true });
    }
  }, [auth, route.name, route.sessionId]);

  useEffect(() => {
    if (!auth?.token) return;
    getCurrentAccount(auth.token)
      .then((result) => setAuth((current) => current ? { ...current, user: result.user } : current))
      .catch(() => {
        sessionStorage.removeItem(AUTH_SESSION_KEY);
        setAuth(null);
      });
  }, [auth?.token]);

  useEffect(() => {
    if (auth?.mode !== 'guest') return undefined;
    const remaining = auth.expiresAt - Date.now();
    if (remaining <= 0) {
      logout();
      return undefined;
    }
    const timer = window.setTimeout(logout, remaining);
    return () => window.clearTimeout(timer);
  }, [auth?.expiresAt, auth?.mode]);

  async function authenticated(value) {
    const signedIn = { ...value, mode: 'account' };
    try {
      const guest = JSON.parse(sessionStorage.getItem(GUEST_CHAT_KEY) || 'null');
      const transferableMessages = Array.isArray(guest?.messages)
        ? guest.messages
          .filter((message) => ['user', 'bot'].includes(message?.role) && message?.text && !['intro', 'prompt'].includes(message?.variant))
          .map((message) => ({ role: message.role, text: message.text }))
        : [];
      if (transferableMessages.some((message) => message.role === 'user')) {
        await importGuestConversation(value.token, transferableMessages);
      }
      sessionStorage.removeItem(GUEST_CHAT_KEY);
    } catch (error) {
      console.warn('Percakapan tamu belum dapat dipindahkan ke akun.', error);
    }
    sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(signedIn));
    setAuth(signedIn);
    navigate('/chat', { replace: true });
  }

  function continueAsGuest() {
    const guest = {
      mode: 'guest',
      expiresAt: Date.now() + GUEST_SESSION_DURATION_MS,
      user: { display_name: 'Tamu', username: 'sesi-sementara', role: 'guest' },
    };
    sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(guest));
    sessionStorage.setItem(GUEST_CHAT_KEY, JSON.stringify({ expiresAt: guest.expiresAt, messages: [] }));
    setAuth(guest);
    navigate('/chat', { replace: true });
  }

  function accountUpdated(user) {
    setAuth((current) => {
      const updated = { ...current, user };
      sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(updated));
      return updated;
    });
  }

  function logout() {
    localStorage.removeItem(PENDING_REQUEST_KEY);
    sessionStorage.removeItem(AUTH_SESSION_KEY);
    try {
      const pendingGuest = JSON.parse(sessionStorage.getItem(GUEST_CHAT_KEY) || 'null');
      if (!pendingGuest?.expiresAt || pendingGuest.expiresAt <= Date.now()) {
        sessionStorage.removeItem(GUEST_CHAT_KEY);
      }
    } catch {
      sessionStorage.removeItem(GUEST_CHAT_KEY);
    }
    setAuth(null);
    navigate('/login', { replace: true });
  }

  return auth
    ? <BotPage auth={auth} route={route} onNavigate={navigate} onLogout={logout} onAccountUpdated={accountUpdated} />
    : (
      <AuthScreen
        mode={route.name === 'register' ? 'register' : 'login'}
        onModeChange={(mode, options) => navigate(mode === 'register' ? '/register' : '/login', options)}
        onAuthenticated={authenticated}
        onContinueAsGuest={continueAsGuest}
      />
    );
}
