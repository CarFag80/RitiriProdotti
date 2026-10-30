/* RitiriProdotti: avvio con attese limitate e cache non bloccante. */
var BASE = new URL("./", self.location.href);
var PREFIX = "ritiriprodotti-" + encodeURIComponent(BASE.pathname) + "-";
var CACHE = PREFIX + "v2";
var NETWORK_MS = 3000, CACHE_MS = 1000;
var INDEX = new URL("index.html", BASE).href;
var DATA = new URL("data.json", BASE).href;
var STATUS = new URL("status.json", BASE).href;
var SHELL = ["manifest.json", "icons/icon-192.png", "icons/icon-512.png", "icons/icon-maskable-192.png", "icons/icon-maskable-512.png"].map(function (p) { return new URL(p, BASE).href; });

function bounded(promise, ms, cancel) {
  return new Promise(function (resolve, reject) {
    var timer = setTimeout(function () {
      if (cancel) cancel();
      reject(new Error("Tempo massimo superato"));
    }, ms);
    Promise.resolve(promise).then(function (value) {
      clearTimeout(timer); resolve(value);
    }, function (error) { clearTimeout(timer); reject(error); });
  });
}

function retrieve(request, kind, ms) {
  var controller = new AbortController();
  return bounded((async function () {
    var response = await fetch(request, { cache: "no-cache", signal: controller.signal });
    if (!response.ok || response.type === "opaque") throw new Error("Risposta HTTP non valida");
    if (kind) {
      var value = await response.clone().json();
      if (kind === "data" && !Array.isArray(value)) throw new Error("Archivio non valido");
      if (kind === "status" && (!value || typeof value !== "object" || Array.isArray(value) || typeof value.outcome !== "string")) throw new Error("Stato non valido");
    }
    return response;
  })(), ms || NETWORK_MS, function () { controller.abort(); });
}

function save(request, response) {
  return bounded((async function () {
    var cache = await caches.open(CACHE);
    await cache.put(request, response);
  })(), CACHE_MS).catch(function (error) { console.warn("Cache non aggiornata", error.message); });
}

async function fallback(request, navigation) {
  try {
    var cached = await bounded((async function () {
      var cache = await caches.open(CACHE);
      return await cache.match(request) || (navigation ? await cache.match(INDEX) : null);
    })(), CACHE_MS);
    if (cached) return cached;
  } catch (error) {}
  if (!navigation) return Response.error();
  return new Response('<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Richiami non disponibili</title><body><h1>Impossibile aprire Richiami</h1><p>La rete o la copia offline non sono disponibili. Riprova tra poco.</p><button onclick="location.reload()">Riprova</button></body></html>', { status: 503, headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" } });
}

self.addEventListener("install", function (event) {
  event.waitUntil((async function () {
    var response = await retrieve(new Request(INDEX), null, 15000);
    var cache = await bounded(caches.open(CACHE), CACHE_MS);
    await bounded(cache.put(INDEX, response), 3000);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", function (event) {
  event.waitUntil((async function () {
    try {
      await bounded((async function () {
        var keys = await caches.keys();
        await Promise.all(keys.filter(function (key) { return key.indexOf(PREFIX) === 0 && key !== CACHE; }).map(function (key) { return caches.delete(key); }));
      })(), CACHE_MS);
    } catch (error) { console.warn("Pulizia cache rinviata"); }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", function (event) {
  var request = event.request, url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== BASE.origin || url.pathname.indexOf(BASE.pathname) !== 0) return;
  var kind = url.pathname === new URL(DATA).pathname ? "data" : url.pathname === new URL(STATUS).pathname ? "status" : null;
  var navigation = request.mode === "navigate";
  if (!kind && !navigation && url.href !== BASE.href && url.href !== INDEX && SHELL.indexOf(url.href) === -1) return;
  var key = navigation ? INDEX : request;
  var network = retrieve(request, kind).then(function (response) {
    return { response: response, copy: response.clone() };
  });
  event.respondWith(network.then(function (result) { return result.response; }).catch(function () { return fallback(key, navigation); }));
  event.waitUntil(network.then(function (result) { return save(key, result.copy); }).catch(function () {}));
});
