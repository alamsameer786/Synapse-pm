export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // 1. Proxy API requests to Render
    if (url.pathname.startsWith('/api/')) {
      const originUrl = env.API_ORIGIN;
      if (!originUrl) return new Response('API_ORIGIN not configured', { status: 500 });
      
      const targetUrl = originUrl + url.pathname + url.search;
      const newRequest = new Request(targetUrl, request);
      const response = await fetch(newRequest);
      
      const newResponse = new Response(response.body, response);
      newResponse.headers.set('Access-Control-Allow-Origin', '*');
      newResponse.headers.set('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
      newResponse.headers.set('Access-Control-Allow-Headers', '*');
      return newResponse;
    }

    // 2. If user goes to the root, serve the user index.html
    if (url.pathname === '/') {
      return env.ASSETS.fetch(new URL('/user/index.html', url.origin));
    }

    // 3. Serve all other files normally (this includes /admin/ and /user/)
    return env.ASSETS.fetch(request);
  }
};
