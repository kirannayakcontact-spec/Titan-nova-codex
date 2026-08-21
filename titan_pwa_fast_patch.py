"""Fast, conservative PWA support for the active legacy dashboard.

The browser keeps successful read responses locally, but mutations always go to
the server.  This deliberately avoids an offline write queue for financial data.
"""

from __future__ import annotations

from flask import Response


PWA_VERSION = "2026.08.21.2"

SERVICE_WORKER = f"""'use strict';
const VERSION = 'titan-pwa-{PWA_VERSION}';
const STATIC_CACHE = VERSION + '-static';
const PAGE_CACHE = VERSION + '-pages';
const STATIC_ASSETS = ['/static/pwa-fast.js?v={PWA_VERSION}', '/icon.svg'];

self.addEventListener('install', event => {{
  event.waitUntil(caches.open(STATIC_CACHE).then(cache => cache.addAll(STATIC_ASSETS)));
  self.skipWaiting();
}});

self.addEventListener('activate', event => {{
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('titan-pwa-') && key !== STATIC_CACHE).map(key => caches.delete(key)))),
    self.clients.claim()
  ]));
}});

self.addEventListener('fetch', event => {{
  const request = event.request;
  const url = new URL(request.url);

  // Never replay or cache writes. Money and settings mutations must be
  // acknowledged by Flask/Firebase before the UI treats them as saved.
  if (request.method !== 'GET') return;

  // API fallback is implemented in IndexedDB by pwa-fast.js. Keeping API JSON
  // out of Cache Storage avoids two competing local sources of truth.
  if (url.origin === self.location.origin && url.pathname.startsWith('/api/')) return;

  // Immutable application assets are cache-first.
  if (url.origin === self.location.origin && (url.pathname.startsWith('/static/') || url.pathname === '/icon.svg')) {{
    event.respondWith(caches.match(request).then(cached => cached || fetch(request).then(response => {{
      if (response.ok) caches.open(STATIC_CACHE).then(cache => cache.put(request, response.clone()));
      return response;
    }})));
    return;
  }}

  // Navigations are network-first so a dashboard deployment cannot be hidden
  // behind a stale cached HTML shell. Cache is only a temporary offline fallback.
  if (request.mode === 'navigate' && url.origin === self.location.origin) {{
    event.respondWith(fetch(request).then(response => {{
      if (response.ok) caches.open(PAGE_CACHE).then(cache => cache.put(request, response.clone()));
      return response;
    }}).catch(() => caches.match(request)));
  }}
}});
"""


def _service_worker_response() -> Response:
    return Response(
        SERVICE_WORKER,
        content_type="application/javascript; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Service-Worker-Allowed": "/",
            "X-Titan-PWA-Version": PWA_VERSION,
        },
    )


def register_titan_pwa_fast(app):
    """Install the upgraded worker and inject the IndexedDB read cache client."""

    sw_endpoint = next(
        (rule.endpoint for rule in app.url_map.iter_rules() if rule.rule == "/sw.js"),
        None,
    )
    if sw_endpoint:
        app.view_functions[sw_endpoint] = _service_worker_response
    else:
        app.add_url_rule("/sw.js", "titan_fast_service_worker", _service_worker_response)

    marker = b'data-titan-pwa-fast="1"'
    script = (
        f'<script data-titan-pwa-fast="1" src="/static/pwa-fast.js?v={PWA_VERSION}"></script>'
    ).encode()

    @app.after_request
    def inject_fast_pwa(response):
        content_type = response.headers.get("Content-Type", "").lower()
        if (
            response.status_code == 200
            and "text/html" in content_type
            and not response.direct_passthrough
        ):
            body = response.get_data()
            if marker not in body:
                if b"</head>" in body:
                    body = body.replace(b"</head>", script + b"</head>", 1)
                else:
                    body = script + body
                response.set_data(body)
                response.headers.pop("Content-Length", None)
        return response

    app.config["TITAN_PWA_FAST_VERSION"] = PWA_VERSION
