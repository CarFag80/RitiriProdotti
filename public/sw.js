/* sw.js - service worker per il funzionamento offline di "Richiami".
   Strategia: cache-first per la shell (index.html, manifest, icone),
   network-first per data.json e status.json con fallback alla cache. */

var CACHE = "richiami-v1";
var SHELL = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-192.png",
  "./icons/icon-maskable-512.png"
];
var DYNAMIC = ["./data.json", "./status.json"];

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(CACHE).then(function (c) {
      return c.addAll(SHELL.concat(DYNAMIC)).catch(function () {
        /* Se data.json/status.json non esistono, ignora: la cache shell basta. */
        return c.addAll(SHELL);
      });
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== "GET") return;

  /* data.json / status.json: network-first, fallback cache. */
  if (DYNAMIC.indexOf(url.pathname.replace(/^\//, "./")) !== -1 || url.pathname.endsWith("data.json") || url.pathname.endsWith("status.json")) {
    e.respondWith(
      fetch(e.request).then(function (resp) {
        var copy = resp.clone();
        caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        return resp;
      }).catch(function () {
        return caches.match(e.request);
      })
    );
    return;
  }

  /* Tutto il resto: cache-first, fallback network. */
  e.respondWith(
    caches.match(e.request).then(function (cached) {
      if (cached) {
        /* Aggiorna in background. */
        fetch(e.request).then(function (resp) {
          if (resp && resp.status === 200) {
            var copy = resp.clone();
            caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
          }
        }).catch(function () {});
        return cached;
      }
      return fetch(e.request).then(function (resp) {
        if (resp && resp.status === 200 && resp.type === "basic") {
          var copy = resp.clone();
          caches.open(CACHE).then(function (c) { c.put(e.request, copy); });
        }
        return resp;
      });
    })
  );
});