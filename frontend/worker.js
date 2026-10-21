export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // 1. Keep the backend on the API hostname working normally.
    if (url.hostname === "api.synapsepm.us.ci") {
      return fetch(request);
    }

    // 2. Proxy API calls from the frontend to Render.
    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      if (!env.API_ORIGIN) {
        return new Response("API_ORIGIN is not configured", { status: 500 });
      }
      const target = new URL(url.pathname + url.search, env.API_ORIGIN);
      return fetch(new Request(target.toString(), request));
    }

    // 3. Serve the site's landing page.
    if (url.pathname === "/") {
      return env.ASSETS.fetch(
        new Request(new URL("/user/index.html", url.origin), request)
      );
    }

    // 4. Serve assets (images, css, js) from the root assets folder.
    // If it starts with /assets/ or has a file extension, serve from root.
    if (url.pathname.startsWith("/assets/") || url.pathname.match(/\.(png|jpg|jpeg|gif|css|js|json|svg|ico|woff|woff2|ttf|eot|mp4)$/)) {
      return env.ASSETS.fetch(request);
    }

    // 5. EVERYTHING ELSE: Serve from the /user/ folder.
    // This fixes the 404s for /login.html, /dashboard.html, etc.
    return env.ASSETS.fetch(
      new Request(new URL("/user" + url.pathname, url.origin), request)
    );
  }
};
