
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Keep the backend on the API hostname working normally.
    if (url.hostname === "api.synapsepm.us.ci") {
      return fetch(request);
    }

    // Proxy API calls from the frontend to Render.
    if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
      if (!env.API_ORIGIN) {
        return new Response("API_ORIGIN is not configured", { status: 500 });
      }

      const target = new URL(url.pathname + url.search, env.API_ORIGIN);
      return fetch(new Request(target.toString(), request));
    }

    // Serve the site's landing page.
    if (url.pathname === "/") {
      return env.ASSETS.fetch(
        new Request(new URL("/user/index.html", url.origin), request)
      );
    }

    // Serve all other frontend pages and assets.
    return env.ASSETS.fetch(request);
  }
};
