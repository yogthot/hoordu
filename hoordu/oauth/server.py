from asyncio import Semaphore
from aiohttp import web


class OAuthServer:
    def __init__(self, port: int):
        self.port: int = port
        self._semaphore: Semaphore = Semaphore(0)
        
        self.app: web.Application = web.Application()
        self.app.add_routes([web.get('/{tail:.*}', self._wait_for_oauth)])
    
    async def _wait_for_oauth(self, request: web.Request) -> web.Response:
        self.path = request.path
        self.params = dict(request.query)
        
        self._semaphore.release()
        
        text = ('<script>window.close()</script>'
                '<h2 style="text-align:center;margin-top:10vh;">You can close this page now.</h2>')
        
        return web.Response(text=text, headers={'Content-Type': 'text/html; charset=UTF-8'})
    
    async def wait_for_request(self) -> tuple[str, dict[str, str]]:
        self._semaphore: Semaphore = Semaphore(0)
        
        runner = web.AppRunner(self.app)
        try:
            await runner.setup()
            site = web.TCPSite(runner, 'localhost', self.port)
            await site.start()
            
            await self._semaphore.acquire()
            
        finally:
            await runner.cleanup()
        
        return self.path, self.params


if __name__ == '__main__':
    async def main() -> None:
        port = 8941
        s = OAuthServer(port)
        print(f'Started the server at: http://localhost:{port}/')
        print(f'Click here to test it: http://localhost:{port}/test?code=1234')
        print(await s.wait_for_request())
    
    import asyncio
    asyncio.run(main())

