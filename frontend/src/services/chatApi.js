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

export async function sendChatQuestion(question, history = [], { signal } = {}) {
  const response = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history: toApiHistory(history) }),
    signal,
  });

  if (!response.ok) {
    throw new Error('Chat request failed');
  }

  const data = await response.json();
  return {
    ...data,
    answer: data.answer || data.reply || '',
    reply: data.reply || data.answer || '',
    sources: Array.isArray(data.sources) ? data.sources : [],
    nextActions: Array.isArray(data.next_actions) ? data.next_actions : [],
  };
}

export async function sendFeedback({ identity, email, feedback }) {
  const response = await fetch(`${API_BASE_URL}/api/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      identity: identity.trim() || null,
      email: email.trim() || null,
      feedback: feedback.trim(),
    }),
  });

  if (!response.ok) {
    let message = 'Feedback belum dapat dikirim. Silakan coba kembali.';
    try {
      const errorData = await response.json();
      if (typeof errorData.detail === 'string') message = errorData.detail;
    } catch {
      // Keep the safe default when the backend does not return JSON.
    }
    throw new Error(message);
  }
  return response.json();
}
