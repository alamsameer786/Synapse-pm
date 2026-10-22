export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // 1. Proxy API calls to Render
    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      if (!env.API_ORIGIN) return new Response("API_ORIGIN is not configured", { status: 500 });
      const target = new URL(url.pathname + url.search, env.API_ORIGIN);
      return fetch(new Request(target.toString(), request));
    }

    // 2. Landing page
    if (url.pathname === "/") {
      return env.ASSETS.fetch(new Request(new URL("/user/index.html", url.origin), request));
    }

    // 3. Images and static assets
    if (url.pathname.startsWith("/assets/") || url.pathname.match(/\.(png|jpg|css|js|json|svg|ico)$/)) {
      return env.ASSETS.fetch(request);
    }

    // 4. Everything else goes to /user/
    return env.ASSETS.fetch(new Request(new URL("/user" + url.pathname, url.origin), request));
  }
};
