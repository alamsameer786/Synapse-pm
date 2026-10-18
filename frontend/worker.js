export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname.startsWith('/api/')) {
      const originUrl = env.API_ORIGIN;
      if (!originUrl) return new Response('API_ORIGIN not configured', { status: 500 });
      
      const targetUrl = originUrl + url.pathname + url.search;
      const newRequest = new Request(targetUrl, request);
      
      // Forward the request to Render
      const response = await fetch(newRequest);
      
      // Create a new response to modify headers (CORS)
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Access-Control-Allow-Origin', '*');
      newResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
      newResponse.headers.set('Access-Control-Allow-Headers', '*');
      
      return newResponse;
    }
    // Serve static files for everything else
    return env.ASSETS.fetch(request);
  }
};
