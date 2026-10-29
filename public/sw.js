/* RitiriProdotti: cache isolate per percorso, rete prioritaria e fallback offline. */
var BASE = new URL("./", self.location.href);
var PREFIX = "ritiriprodotti-" + encodeURIComponent(BASE.pathname) + "-";
var CACHE = PREFIX + "v2";
var SHELL = ["./", "./index.html", "./manifest.json", "./icons/icon-192.png", "./icons/icon-512.png", "./icons/icon-maskable-192.png", "./icons/icon-maskable-512.png"].map(function (p) { return new URL(p, BASE).href; });
var DATA = new URL("data.json", BASE).href;
var STATUS = new URL("status.json", BASE).href;

async function save(request, response) {
  try {
    var cache = await caches.open(CACHE);
    await cache.put(request, response.clone());
  } catch (error) {
    console.warn("Cache non aggiornata", error);
  }
}

async function validate(response, kind) {
  if (!response.ok || response.type === "opaque") throw new Error("Risposta HTTP non valida");
  if (kind) {
    var value = await response.clone().json();
    if (kind === "data" && !Array.isArray(value)) throw new Error("Archivio non valido");
    if (kind === "status" && (!value || typeof value !== "object" || Array.isArray(value) || typeof value.outcome !== "string")) throw new Error("Stato non valido");
  }
  return response;
}

async function networkFirst(request, kind, navigation) {
  try {
    var response = await validate(await fetch(request, { cache: "no-cache" }), kind);
    await save(request, response);
    return response;
  } catch (error) {
    var cache = await caches.open(CACHE);
    var cached = await cache.match(request);
    if (!cached && navigation) cached = await cache.match(new URL("index.html", BASE).href);
    if (cached) return cached;
    return Response.error();
  }
}

self.addEventListener("install", function (event) {
  event.waitUntil((async function () {
    var cache = await caches.open(CACHE);
    await cache.addAll(SHELL);
    await Promise.all([
      networkFirst(new Request(DATA), "data", false),
      networkFirst(new Request(STATUS), "status", false)
    ]);
    await self.skipWaiting();
  })());
});

self.addEventListener("activate", function (event) {
  event.waitUntil((async function () {
    var keys = await caches.keys();
    await Promise.all(keys.filter(function (key) {
      return key.indexOf(PREFIX) === 0 && key !== CACHE;
    }).map(function (key) { return caches.delete(key); }));
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  var url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== BASE.origin || url.pathname.indexOf(BASE.pathname) !== 0) return;
  var kind = url.pathname === new URL(DATA).pathname ? "data" : url.pathname === new URL(STATUS).pathname ? "status" : null;
  var navigation = request.mode === "navigate";
  var known = SHELL.indexOf(url.href) !== -1;
  if (!kind && !navigation && !known) return;
  var task = networkFirst(request, kind, navigation);
  event.respondWith(task);
  event.waitUntil(task.then(function () {}, function () {}));
});
