export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

function toApiHistory(messages) {
  if (!Array.isArray(messages)) return [];

  return messages
    .filter((message) => message && ['user', 'bot'].includes(message.role) && message.text)
    .slice(-6)
    .map((message) => ({
      role: message.role,
      text: String(message.text).replace(/\s+/g, ' ').trim().slice(0, 1200),
    }))
    .filter((message) => message.text.length > 0);
}

async function apiRequest(path, { token, headers = {}, ...options } = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'Permintaan belum dapat diproses.');
    error.status = response.status;
    throw error;
  }
  return data;
}

export function loginAccount(username, password) {
  return apiRequest('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
}

export function registerAccount({ username, displayName, password, privacyAccepted }) {
  return apiRequest('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      username,
      display_name: displayName,
      password,
      privacy_accepted: privacyAccepted,
    }),
  });
}

export function getCurrentAccount(token) {
  return apiRequest('/api/auth/me', { token });
}

export function getPrivacyNotice() {
  return apiRequest('/api/privacy');
}

export function listSessions(token) {
  return apiRequest('/api/sessions', { token });
}

export function createSession(token, title = 'Percakapan baru') {
  return apiRequest('/api/sessions', {
    token,
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export function getSessionMessages(token, sessionId) {
  return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, { token });
}

export function deleteSession(token, sessionId) {
  return apiRequest(`/api/sessions/${encodeURIComponent(sessionId)}`, { token, method: 'DELETE' });
}

export async function sendChatQuestion(question, history = [], { signal, token, sessionId } = {}) {
  const data = await apiRequest('/api/chat', {
    token,
    method: 'POST',
    body: JSON.stringify({ question, history: toApiHistory(history), session_id: sessionId || null }),
    signal,
  });
  return {
    ...data,
    answer: data.answer || data.reply || '',
    reply: data.reply || data.answer || '',
    sources: Array.isArray(data.sources) ? data.sources : [],
    nextActions: Array.isArray(data.next_actions) ? data.next_actions : [],
  };
}

export async function sendFeedback({ identity, email, feedback }) {
  return apiRequest('/api/feedback', {
    method: 'POST',
    body: JSON.stringify({
      identity: identity.trim() || null,
      email: email.trim() || null,
      feedback: feedback.trim(),
    }),
  });
}
