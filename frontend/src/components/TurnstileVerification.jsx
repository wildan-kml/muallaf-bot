import React, { useEffect, useRef } from 'react';


const SCRIPT_ID = 'cloudflare-turnstile-script';


export default function TurnstileVerification({ siteKey, onToken, onError }) {
  const containerRef = useRef(null);
  const widgetRef = useRef(null);

  useEffect(() => {
    if (!siteKey || !containerRef.current) return undefined;
    let cancelled = false;

    const render = () => {
      if (cancelled || !containerRef.current || !window.turnstile || widgetRef.current !== null) return;
      widgetRef.current = window.turnstile.render(containerRef.current, {
        sitekey: siteKey,
        theme: 'light',
        size: 'flexible',
        callback: onToken,
        'error-callback': () => onError('Verifikasi keamanan gagal dimuat. Silakan muat ulang halaman.'),
        'expired-callback': () => onError('Verifikasi keamanan kedaluwarsa. Silakan ulangi.'),
      });
    };

    let script = document.getElementById(SCRIPT_ID);
    if (!script) {
      script = document.createElement('script');
      script.id = SCRIPT_ID;
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
    script.addEventListener('load', render);
    render();
    return () => {
      cancelled = true;
      script?.removeEventListener('load', render);
      if (widgetRef.current !== null && window.turnstile) window.turnstile.remove(widgetRef.current);
      widgetRef.current = null;
    };
  }, [siteKey, onToken, onError]);

  return <div className="turnstile-verification" ref={containerRef} aria-label="Verifikasi keamanan" />;
}
