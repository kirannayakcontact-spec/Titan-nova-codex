(() => {
  'use strict';

  const VERSION = '2026.07.22.1';
  const DB_NAME = 'titan-nova-local';
  const STORE = 'safe-get-cache';
  const DB_VERSION = 1;
  const NETWORK_TIMEOUT_MS = 1800;
  const MAX_AGE_MS = 24 * 60 * 60 * 1000;
  const nativeFetch = window.fetch.bind(window);

  const isSafeStateRead = request => {
    if (request.method !== 'GET') return false;
    const url = new URL(request.url, location.href);
    if (url.origin !== location.origin) return false;
    return url.pathname === '/api/state' || url.pathname === '/api/market_registry';
  };

  const openDatabase = () => new Promise((resolve, reject) => {
    if (!('indexedDB' in window)) return reject(new Error('IndexedDB unavailable'));
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      if (!database.objectStoreNames.contains(STORE)) database.createObjectStore(STORE, { keyPath: 'key' });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  const cacheKey = request => new URL(request.url, location.href).href;

  const readCache = async request => {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
      const tx = database.transaction(STORE, 'readonly');
      const query = tx.objectStore(STORE).get(cacheKey(request));
      query.onsuccess = () => resolve(query.result || null);
      query.onerror = () => reject(query.error);
      tx.oncomplete = () => database.close();
    });
  };

  const writeCache = async (request, response) => {
    if (!response.ok) return;
    const contentType = response.headers.get('Content-Type') || '';
    if (!contentType.includes('application/json')) return;
    const body = await response.clone().text();
    JSON.parse(body); // Only persist valid JSON.
    const database = await openDatabase();
    await new Promise((resolve, reject) => {
      const tx = database.transaction(STORE, 'readwrite');
      tx.objectStore(STORE).put({ key: cacheKey(request), body, savedAt: Date.now() });
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
    database.close();
  };

  const cachedResponse = record => {
    if (!record || Date.now() - Number(record.savedAt || 0) > MAX_AGE_MS) return null;
    return new Response(record.body, {
      status: 200,
      headers: { 'Content-Type': 'application/json', 'X-Titan-Data-Source': 'indexeddb' }
    });
  };

  window.fetch = async (input, init) => {
    const request = new Request(input, init);
    if (!isSafeStateRead(request)) return nativeFetch(input, init);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), NETWORK_TIMEOUT_MS);
    try {
      const response = await nativeFetch(request, { signal: controller.signal });
      clearTimeout(timeout);
      writeCache(request, response).catch(() => {});
      return response;
    } catch (error) {
      clearTimeout(timeout);
      const local = cachedResponse(await readCache(request).catch(() => null));
      if (local) {
        window.dispatchEvent(new CustomEvent('titan:cached-state'));
        return local;
      }
      throw error;
    }
  };

  const showStatus = text => {
    let badge = document.getElementById('titan-connectivity-badge');
    if (!badge) {
      badge = document.createElement('div');
      badge.id = 'titan-connectivity-badge';
      badge.style.cssText = 'position:fixed;right:10px;top:10px;z-index:2147483647;padding:6px 10px;border-radius:999px;background:#17212b;color:#fff;font:700 11px system-ui;box-shadow:0 4px 16px #0005';
      document.body.appendChild(badge);
    }
    badge.textContent = text;
    badge.hidden = false;
    clearTimeout(showStatus.timer);
    showStatus.timer = setTimeout(() => { badge.hidden = navigator.onLine; }, 2800);
  };

  addEventListener('offline', () => showStatus('Offline • local read mode'));
  addEventListener('online', () => showStatus('Online • syncing'));
  addEventListener('titan:cached-state', () => showStatus('Fast local data • syncing later'));
  addEventListener('DOMContentLoaded', () => {
    if (!navigator.onLine) showStatus('Offline • local read mode');
    if ('serviceWorker' in navigator) navigator.serviceWorker.register(`/sw.js?v=${VERSION}`).catch(() => {});
  });
})();
