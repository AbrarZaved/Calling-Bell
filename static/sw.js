// Service worker: shows the notification even when /receive is closed.
self.addEventListener("install", (event) => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (e) {
    data = { message: event.data ? event.data.text() : "" };
  }
  const body = data.message || "Someone is at the door!";

  event.waitUntil(
    self.registration.showNotification("\uD83D\uDD14 Home Calling Bell", {
      body,
      tag: "home-bell",
      renotify: true,
      requireInteraction: true,
      vibrate: [300, 150, 300, 150, 500],
      data: { url: "/bell/receive" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || "/bell/receive";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (client.url.includes("/receive") && "focus" in client) return client.focus();
      }
      return self.clients.openWindow(target);
    })
  );
});
