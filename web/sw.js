// Service worker de Ropero. Primero red, con la caché solo como respaldo sin conexión.
// /api/ y /img/ nunca se guardan, para no mostrar prendas desactualizadas.
// Al cambiar archivos de web/ no hace falta tocar nada: la red siempre gana cuando hay conexión.
const CACHE = 'ropero-v1';
const BASICOS = ['/', '/campos', '/static/styles.css', '/static/app.js', '/static/campos.js', '/static/icon-192.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => Promise.all(BASICOS.map((url) => cache.add(url).catch(() => {}))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((claves) => Promise.all(claves.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/img/')) return;
  const clave = url.pathname;   // sin query: "/?q=camisa" y "/" comparten la misma entrada
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok && res.type === 'basic') {
          const copia = res.clone();
          caches.open(CACHE).then((cache) => cache.put(clave, copia));
        }
        return res;
      })
      .catch(() => caches.match(clave))
  );
});
