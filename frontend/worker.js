
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Handle API preflight requests.
    if (url.pathname.startsWith("/api/")) {
      const origin = env.API_ORIGIN;

      if (!origin) {
        return new Response("API_ORIGIN not configured", { status: 500 });
      }

      const target = new URL(url.pathname + url.search, origin);

      const headers = new Headers(request.headers);
      headers.delete("host");

      const apiRequest = new Request(target.toString(), request);
      const apiResponse = await fetch(apiRequest);

      const responseHeaders = new Headers(apiResponse.headers);
      const requestOrigin = request.headers.get("Origin");

      if (
        requestOrigin === "https://synapsepm.us.ci" ||
        requestOrigin === "https://www.synapsepm.us.ci"
      ) {
        responseHeaders.set("Access-Control-Allow-Origin", requestOrigin);
        responseHeaders.set("Vary", "Origin");
        responseHeaders.set(
          "Access-Control-Allow-Methods",
          "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        );
        responseHeaders.set(
          "Access-Control-Allow-Headers",
          request.headers.get("Access-Control-Request-Headers") || "Content-Type, Authorization"
        );
      }

      return new Response(apiResponse.body, {
        status: apiResponse.status,
        statusText: apiResponse.statusText,
        headers: responseHeaders
      });
    }

    // Serve the user landing page from the frontend asset directory.
    if (url.pathname === "/") {
      return env.ASSETS.fetch(
        new Request(new URL("/user/index.html", url.origin), request)
      );
    }

    // Serve login, admin, CSS, JS, images, and other static assets.
    return env.ASSETS.fetch(request);
  }
};
