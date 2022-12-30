import asyncio
from aiohttp import web


class OAuthServer:
    def __init__(self, port: int):
        self.port: int = port
        self._waiting: bool = False
        
        self.app: web.Application = web.Application()
        self.app.add_routes([web.get('/{tail:.*}', self._wait_for_oauth)])
    
    async def _wait_for_oauth(self, request: web.Request) -> web.Response:
        self.path = request.path
        self.params = dict(request.query)
        self._waiting = False
        
        text = ('<script>window.close()</script>'
                '<h2 style="text-align:center;margin-top:10vh;">You can close this page now.</h2>')
        
        return web.Response(text=text, headers={'Content-Type': 'text/html; charset=UTF-8'})
    
    async def wait_for_request(self) -> tuple[str, dict[str, str]]:
        self._waiting = True
        
        runner = web.AppRunner(self.app)
        try:
            await runner.setup()
            site = web.TCPSite(runner, 'localhost', self.port)
            await site.start()
            
            while self._waiting:
                await asyncio.sleep(1)
            
        finally:
            await runner.cleanup()
        
        return self.path, self.params


if __name__ == '__main__':
    async def main() -> None:
        s = OAuthServer(8941)
        print(await s.wait_for_request())
    
    asyncio.run(main())

