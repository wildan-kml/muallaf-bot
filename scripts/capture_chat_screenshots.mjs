import { spawn } from 'node:child_process';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const frontendUrl = process.env.SCREENSHOT_FRONTEND_URL || 'http://127.0.0.1:4173/';
const backendUrl = process.env.SCREENSHOT_BACKEND_URL || 'http://127.0.0.1:8000';
const outputDir = path.resolve(process.env.SCREENSHOT_OUTPUT_DIR || 'docs/screenshots');
const chromePath = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const debuggingPort = 9223;
const initialOnly = process.env.SCREENSHOT_INITIAL_ONLY === '1';
const verifyPendingSession = process.env.VERIFY_PENDING_SESSION === '1';

const scenarios = [
  {
    id: 'substantive',
    file: '03-mobile-substantive.png',
    question: 'Apa makna dua kalimat syahadat bagi seorang Muslim?',
  },
  {
    id: 'ambiguous',
    file: '04-mobile-ambiguous-clarification.png',
    question: 'Bagaimanacaranya',
  },
  {
    id: 'personal-legal',
    file: '05-mobile-personal-legal.png',
    question: 'Ayah saya meninggal dan meninggalkan rumah serta tabungan. Siapa yang berhak dan berapa bagiannya?',
  },
  {
    id: 'crisis',
    file: '06-mobile-crisis.png',
    question: 'Saya merasa putus asa dan tidak ingin melanjutkan hidup.',
  },
  {
    id: 'out-of-scope',
    file: '07-mobile-out-of-scope.png',
    question: 'Hotel apa yang paling bagus untuk liburan di Bali?',
  },
];

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function waitForDebugger() {
  const endpoint = `http://127.0.0.1:${debuggingPort}/json/version`;
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const response = await fetch(endpoint);
      if (response.ok) return;
    } catch {
      // Chrome may need a moment to expose its debugging endpoint.
    }
    await delay(100);
  }
  throw new Error('Chrome debugging endpoint did not become ready.');
}

async function createPage() {
  const response = await fetch(
    `http://127.0.0.1:${debuggingPort}/json/new?${encodeURIComponent(frontendUrl)}`,
    { method: 'PUT' },
  );
  if (!response.ok) throw new Error(`Unable to create Chrome page: ${response.status}`);
  return response.json();
}

function connectCdp(webSocketDebuggerUrl) {
  const socket = new WebSocket(webSocketDebuggerUrl);
  let nextId = 1;
  const pending = new Map();

  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  });

  const ready = new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });

  return {
    ready,
    close: () => socket.close(),
    send(method, params = {}) {
      const id = nextId;
      nextId += 1;
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        socket.send(JSON.stringify({ id, method, params }));
      });
    },
  };
}

async function requestAnswer(question) {
  const response = await fetch(`${backendUrl}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, history: [] }),
  });
  if (!response.ok) throw new Error(`Chat API returned ${response.status} for: ${question}`);
  return response.json();
}

function screenshotMessages(question, response) {
  return [
    {
      id: 'intro',
      role: 'bot',
      text: "Assalamu'alaikum, saya Muallaf Bot. Apa yang ingin kamu tanyakan hari ini?",
      time: '13.52',
      sources: [],
    },
    { id: 'question', role: 'user', text: question, time: '13.52', sources: [] },
    {
      id: 'answer',
      role: 'bot',
      text: response.answer,
      time: '13.52',
      sources: response.mode === 'fallback' ? [] : response.sources,
    },
  ];
}

async function capture(
  page,
  messages,
  fileName,
  viewport,
  {
    openSidebar = false,
    showIntroduction = false,
    showFeedback = false,
    showFeedbackSuccess = false,
    showResetNotice = false,
    openViewer = false,
  } = {},
) {
  const cdp = connectCdp(page.webSocketDebuggerUrl);
  await cdp.ready;
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: viewport.width,
    height: viewport.height,
    deviceScaleFactor: 1,
    mobile: viewport.mobile,
    screenWidth: viewport.width,
    screenHeight: viewport.height,
  });
  await cdp.send('Page.navigate', { url: frontendUrl });
  await delay(700);

  const serializedMessages = JSON.stringify(messages);
  await cdp.send('Runtime.evaluate', {
    expression: `localStorage.setItem('imc-mask-public-chat-history-v2', ${JSON.stringify(serializedMessages)}); location.reload();`,
  });
  await delay(900);
  await cdp.send('Runtime.evaluate', {
    expression: `(() => {
      window.scrollTo(0, 0);
      if (!${showIntroduction}) document.querySelector('.introduction-close')?.click();
      if (${showFeedback || showFeedbackSuccess}) document.querySelector('.feedback-button')?.click();
      if (${showResetNotice}) document.querySelector('.reset-chat-button')?.click();
      if (${openViewer}) document.querySelector('.source-link')?.click();
      const list = document.querySelector('.chat-list');
      if (list) list.scrollTop = ${messages.length > 1 ? 'list.scrollHeight' : '0'};
      if (${openSidebar}) document.querySelector('.bot-sidebar-toggle')?.click();
    })();`,
  });
  await delay(250);
  if (openViewer) await delay(2500);

  if (showFeedbackSuccess) {
    await cdp.send('Runtime.evaluate', {
      expression: `(() => {
        localStorage.removeItem('muallaf-bot-feedback-cooldown-until-v1');
        window.fetch = async () => new Response(JSON.stringify({ status: 'ok', message: 'Terima kasih. Feedback Anda telah dikirim melalui email.' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
        const setValue = (element, value) => {
          const prototype = element instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
          Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, value);
          element.dispatchEvent(new Event('input', { bubbles: true }));
          element.dispatchEvent(new Event('change', { bubbles: true }));
        };
        setValue(document.querySelector('input[type="email"]'), 'pengguna@example.com');
        setValue(document.querySelector('.feedback-form textarea'), 'Tampilan Muallaf Bot mudah digunakan.');
        setTimeout(() => document.querySelector('.feedback-form')?.requestSubmit(), 80);
      })()`,
    });
    await delay(700);
  }

  const result = await cdp.send('Page.captureScreenshot', {
    format: 'png',
    fromSurface: true,
    captureBeyondViewport: false,
  });
  await writeFile(path.join(outputDir, fileName), Buffer.from(result.data, 'base64'));
  cdp.close();
  const closeResponse = await fetch(
    `http://127.0.0.1:${debuggingPort}/json/close/${encodeURIComponent(page.id)}`,
  );
  if (!closeResponse.ok) {
    throw new Error(`Unable to close Chrome page after capturing ${fileName}.`);
  }
}

async function verifyOpeningDelayAndBackdropDismissal() {
  const page = await createPage();
  const cdp = connectCdp(page.webSocketDebuggerUrl);
  await cdp.ready;
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.navigate', { url: frontendUrl });
  await delay(700);
  await cdp.send('Runtime.evaluate', {
    expression: `localStorage.removeItem('imc-mask-public-chat-history-v2'); localStorage.removeItem('imc-mask-public-pending-request-v1'); location.reload();`,
  });
  await delay(700);

  await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('.introduction-backdrop')?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))`,
  });
  await delay(300);
  const closeIntro = await cdp.send('Runtime.evaluate', {
    expression: `({ introClosed: !document.querySelector('.introduction-dialog'), loading: Boolean(document.querySelector('.thinking')) })`,
    returnByValue: true,
  });
  if (!closeIntro.result.value.introClosed || !closeIntro.result.value.loading) {
    throw new Error(`Introduction backdrop or opening loader failed: ${JSON.stringify(closeIntro.result.value)}`);
  }

  await delay(1000);
  const promptTooEarly = await cdp.send('Runtime.evaluate', {
    expression: `Boolean(document.querySelector('.message-suggestions'))`,
    returnByValue: true,
  });
  if (promptTooEarly.result.value) throw new Error('Opening suggestions appeared before the three-second delay.');

  await delay(4000);
  const introAfterDelay = await cdp.send('Runtime.evaluate', {
    expression: `document.body.innerText.includes("Assalamu'alaikum, saya Muallaf Bot") && Boolean(document.querySelector('.thinking')) && !document.querySelector('.message-suggestions')`,
    returnByValue: true,
  });
  if (!introAfterDelay.result.value) throw new Error('The first introduction message did not appear after five seconds.');

  await delay(3200);
  const promptAfterDelay = await cdp.send('Runtime.evaluate', {
    expression: `Boolean(document.querySelector('.message-suggestions')) && !document.querySelector('.thinking')`,
    returnByValue: true,
  });
  if (!promptAfterDelay.result.value) throw new Error('Opening suggestions did not replace the second loader after three seconds.');

  await cdp.send('Runtime.evaluate', { expression: `document.querySelector('.feedback-button')?.click()` });
  await delay(300);
  const feedbackOpened = await cdp.send('Runtime.evaluate', {
    expression: `Boolean(document.querySelector('.feedback-dialog'))`,
    returnByValue: true,
  });
  await cdp.send('Runtime.evaluate', {
    expression: `document.querySelector('.feedback-backdrop')?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))`,
  });
  await delay(300);
  const feedbackClosed = await cdp.send('Runtime.evaluate', {
    expression: `!document.querySelector('.feedback-dialog')`,
    returnByValue: true,
  });
  if (!feedbackOpened.result.value || !feedbackClosed.result.value) {
    throw new Error('Feedback modal did not open or close from a backdrop click.');
  }

  await cdp.send('Runtime.evaluate', { expression: `document.querySelector('.reset-chat-button')?.click()` });
  await delay(300);
  const resetNoticeOpened = await cdp.send('Runtime.evaluate', {
    expression: `Boolean(document.querySelector('.status-dialog')) && !document.body.innerText.includes("Assalamu'alaikum, saya Muallaf Bot")`,
    returnByValue: true,
  });
  if (!resetNoticeOpened.result.value) throw new Error('Reset confirmation did not replace the old chat.');

  await delay(5100);
  const resetNoticeClosed = await cdp.send('Runtime.evaluate', {
    expression: `!document.querySelector('.status-dialog') && document.body.innerText.includes("Assalamu'alaikum, saya Muallaf Bot")`,
    returnByValue: true,
  });
  if (!resetNoticeClosed.result.value) throw new Error('Reset confirmation did not close into a fresh introduction.');

  cdp.close();
  const closeResponse = await fetch(
    `http://127.0.0.1:${debuggingPort}/json/close/${encodeURIComponent(page.id)}`,
  );
  if (!closeResponse.ok) throw new Error('Unable to close Chrome page after interaction verification.');
}

async function checkPendingSessionSurvivesReload() {
  const page = await createPage();
  const cdp = connectCdp(page.webSocketDebuggerUrl);
  await cdp.ready;
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('Page.navigate', { url: frontendUrl });
  await delay(700);

  const createdAt = new Date().toISOString();
  const messages = [
    { id: 'crisis', role: 'user', text: 'Saya ingin bunuh diri.', time: '16.32', createdAt, sources: [] },
    {
      id: 'crisis-answer',
      role: 'bot',
      text: 'Keselamatan Anda yang paling utama. Hubungi orang tepercaya sekarang.',
      time: '16.32',
      createdAt,
      sources: [],
    },
    { id: 'follow-up', role: 'user', text: 'Gamau. Bye', time: '16.34', createdAt, sources: [] },
  ];
  const pending = {
    id: 'pending-session-check',
    question: 'Gamau. Bye',
    history: [
      { role: 'user', text: 'Saya ingin bunuh diri.' },
      { role: 'bot', text: 'Keselamatan Anda yang paling utama. Hubungi orang tepercaya sekarang.' },
    ],
    startedAt: Date.now(),
  };

  await cdp.send('Runtime.evaluate', {
    expression: `localStorage.setItem('imc-mask-public-chat-history-v2', ${JSON.stringify(JSON.stringify(messages))}); localStorage.setItem('imc-mask-public-pending-request-v1', ${JSON.stringify(JSON.stringify(pending))}); location.reload();`,
  });
  await delay(900);

  const firstCheck = await cdp.send('Runtime.evaluate', {
    expression: `({ thinking: Boolean(document.querySelector('.thinking')), pending: Boolean(localStorage.getItem('imc-mask-public-pending-request-v1')), body: document.body.innerText.slice(-500) })`,
    returnByValue: true,
  });
  if (!firstCheck.result.value.thinking || !firstCheck.result.value.pending) {
    throw new Error(`Pending indicator was not restored after the first reload: ${JSON.stringify(firstCheck.result.value)}`);
  }

  await cdp.send('Runtime.evaluate', { expression: 'location.reload();' });
  await delay(900);
  const secondCheck = await cdp.send('Runtime.evaluate', {
    expression: `({ thinking: Boolean(document.querySelector('.thinking')), pending: Boolean(localStorage.getItem('imc-mask-public-pending-request-v1')) })`,
    returnByValue: true,
  });
  if (!secondCheck.result.value.thinking || !secondCheck.result.value.pending) {
    throw new Error(`Pending indicator was not restored after the second reload: ${JSON.stringify(secondCheck.result.value)}`);
  }

  await delay(5000);
  const completedCheck = await cdp.send('Runtime.evaluate', {
    expression: `!document.querySelector('.thinking') && !localStorage.getItem('imc-mask-public-pending-request-v1') && document.body.innerText.includes('Keselamatan Anda yang paling utama')`,
    returnByValue: true,
  });
  if (!completedCheck.result.value) throw new Error('Restored request did not complete cleanly after the minimum delay.');

  cdp.close();
  const closeResponse = await fetch(
    `http://127.0.0.1:${debuggingPort}/json/close/${encodeURIComponent(page.id)}`,
  );
  if (!closeResponse.ok) throw new Error('Unable to close Chrome page after pending-session verification.');
}

await mkdir(outputDir, { recursive: true });
const profileDir = await mkdtemp(path.join(tmpdir(), 'muallaf-bot-screenshots-'));
const chrome = spawn(
  chromePath,
  [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    `--remote-debugging-port=${debuggingPort}`,
    `--user-data-dir=${profileDir}`,
    'about:blank',
  ],
  { stdio: 'ignore' },
);

try {
  await waitForDebugger();
  await verifyOpeningDelayAndBackdropDismissal();
  const initialMessages = [
    {
      id: 'intro',
      role: 'bot',
      variant: 'intro',
      text: "Assalamu'alaikum, saya Muallaf Bot. Saya siap membantu informasi awal seputar proses menjadi muslim, syahadat, ibadah dasar, pembinaan mualaf, dan pendampingan IMC-MASK.",
      time: '13.52',
      sources: [],
    },
    {
      id: 'prompt',
      role: 'bot',
      variant: 'prompt',
      text: 'Apa yang ingin kamu tanyakan hari ini?',
      time: '13.52',
      sources: [],
      suggestions: [
        'Apa saja hal dasar yang perlu dipahami calon mualaf?',
        'Saya baru tertarik mengenal Islam, sebaiknya mulai dari mana?',
        'Bagaimana cara belajar Islam jika masih banyak yang belum saya pahami?',
      ],
    },
  ];
  const structuredMessages = [
    {
      id: 'structured-question',
      role: 'user',
      text: 'Berikan contoh ayat dan urutan belajar ibadah dasar.',
      time: '13.52',
      sources: [],
    },
    {
      id: 'structured-answer',
      role: 'bot',
      text: "Salah satu ayat Al-Qur'an yang menjadi rujukan adalah Surat An-Nahl [16] ayat 98. فَإِذَا قَرَأْتَ الْقُرْآنَ فَاسْتَعِذْ بِاللَّهِ مِنَ الشَّيْطَانِ الرَّجِيمِ Artinya: Apabila engkau hendak membaca Al-Qur'an, mohonlah perlindungan kepada Allah dari setan yang terkutuk. Berikut urutan belajarnya: 1. **Mengenal hadas dan najis**: pahami dasar bersuci. 2. **Mempelajari wudu**: ikuti langkah secara berurutan - Membasuh tangan - Berkumur - Mengusap kepala. 3. **Mempelajari salat**: praktikkan dengan pendamping.",
      time: '13.52',
      sources: [],
    },
  ];
  const viewerMessages = [
    {
      id: 'viewer-answer',
      role: 'bot',
      text: 'Syahadat merupakan persaksian keimanan seorang Muslim.',
      time: '13.52',
      sources: [
        {
          chunk_id: 'viewer-source',
          document_title: 'Modul Pembinaan Mualaf',
          file_name: 'Modul Pembinaan Mualaf.pdf',
          page_number: 47,
        },
        {
          chunk_id: 'viewer-website-source',
          document_title: 'Website International Muallaf Center Masjid Agung Sunda Kelapa (IMC-MASK)',
          file_name: 'imc-mask-website',
          source_type: 'website',
          reference_label: 'Alur ikrar syahadat IMC-MASK',
        },
      ],
    },
  ];
  await capture(
    await createPage(),
    initialMessages,
    '00-introduction.png',
    { width: 1440, height: 1000, mobile: false },
    { showIntroduction: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '00-feedback.png',
    { width: 900, height: 720, mobile: false },
    { showFeedback: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '00-feedback-success.png',
    { width: 900, height: 720, mobile: false },
    { showFeedbackSuccess: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '00-reset-notice.png',
    { width: 900, height: 720, mobile: false },
    { showResetNotice: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '00-desktop-initial.png',
    { width: 1440, height: 1000, mobile: false },
  );
  await capture(
    await createPage(),
    initialMessages,
    '01-mobile-initial.png',
    { width: 390, height: 844, mobile: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '01b-mobile-sidebar.png',
    { width: 390, height: 844, mobile: true },
    { openSidebar: true },
  );
  await capture(
    await createPage(),
    viewerMessages,
    '10-desktop-document-viewer.png',
    { width: 1440, height: 900, mobile: false },
    { openViewer: true },
  );
  await capture(
    await createPage(),
    viewerMessages,
    '11-mobile-document-viewer.png',
    { width: 390, height: 844, mobile: true },
    { openViewer: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '01c-mobile-introduction-short.png',
    { width: 390, height: 520, mobile: true },
    { showIntroduction: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '01d-mobile-feedback-short.png',
    { width: 390, height: 520, mobile: true },
    { showFeedback: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '01e-mobile-narrow.png',
    { width: 320, height: 700, mobile: true },
  );
  await capture(
    await createPage(),
    initialMessages,
    '01f-mobile-narrow-sidebar.png',
    { width: 320, height: 700, mobile: true },
    { openSidebar: true },
  );
  await capture(
    await createPage(),
    structuredMessages,
    '08-desktop-structured-content.png',
    { width: 1440, height: 1000, mobile: false },
  );
  await capture(
    await createPage(),
    structuredMessages,
    '09-mobile-structured-content.png',
    { width: 390, height: 844, mobile: true },
  );

  if (verifyPendingSession) {
    await checkPendingSessionSurvivesReload();
  }

  if (!initialOnly) {
    const responses = [];
    for (const scenario of scenarios) {
      responses.push({ ...scenario, response: await requestAnswer(scenario.question) });
    }

    const substantive = responses[0];
    await capture(
      await createPage(),
      screenshotMessages(substantive.question, substantive.response),
      '02-desktop-substantive.png',
      { width: 1440, height: 1000, mobile: false },
    );

    for (const scenario of responses) {
      await capture(
        await createPage(),
        screenshotMessages(scenario.question, scenario.response),
        scenario.file,
        { width: 390, height: 844, mobile: true },
      );
    }

    const summary = responses.map(({ id, file, question, response }) => ({
      id,
      file,
      question,
      mode: response.mode,
      escalation: response.escalation,
      sourceCount: response.sources?.length || 0,
    }));
    await writeFile(path.join(outputDir, 'responses.json'), `${JSON.stringify(summary, null, 2)}\n`);
  }
} finally {
  if (chrome.exitCode === null) {
    const exited = new Promise((resolve) => chrome.once('exit', resolve));
    chrome.kill();
    await Promise.race([exited, delay(2000)]);
  }
  await rm(profileDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
}
