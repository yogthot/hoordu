from typing import Any, Optional
from collections.abc import Awaitable

import aiohttp
from urllib.parse import urlencode, quote
from oauthlib.common import generate_token
import secrets
import base64
import hashlib

__all__ = [
    'OAuth',
    'OAuthError'
]

CODE_CHALLENGE_LENGTH = 43


class OAuthError(Exception):
    pass


# TODO could make the session instantiate this so it shares the default requests implementation
class OAuth:
    def __init__(self, *,
        client_id: str,
        client_secret: str,
        auth_url: str,
        token_url: str,
        redirect_uri: str,
        scopes: str,
        code_challenge_method: Optional[str] = None
    ):
        self._client_id: str = client_id
        self._client_secret: str = client_secret
        self._auth_url: str = auth_url
        self._token_url: str = token_url
        self._redirect_uri: str = redirect_uri
        self._scopes: str = scopes
        self._code_challenge_method: str | None = code_challenge_method
    
    def auth_url(self, *,
        use_state: bool = False,
        use_code_verifier: bool = False,
        extra_args: Optional[dict[str, str]] = None
    ) -> tuple[str, Optional[str], Optional[str]]:
        if use_code_verifier:
            use_state = True
        
        state = generate_token()
        challenge_code = secrets.token_urlsafe(CODE_CHALLENGE_LENGTH)
        
        args = {}
        if extra_args is not None:
            args.update(extra_args)
        
        args.update({
            'response_type': 'code',
            'client_id': self._client_id,
            'redirect_uri': self._redirect_uri,
            'scope': self._scopes
        })
        
        if use_state:
            args.update(state=state)
            
        if use_code_verifier:
            args.update(code_challenge_method=self._code_challenge_method)
            
            if self._code_challenge_method == 'plain':
                args.update(code_challenge=challenge_code)
                
            else:
                h = hashlib.sha256()
                h.update(challenge_code.encode('ascii'))
                digest = h.digest()
                # urlsafe_b64encode: substitutes - instead of + and _ instead of / in the standard Base64 alphabet
                challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
                args.update(code_challenge=challenge)
        
        url = f'{self._auth_url}?{urlencode(args, quote_via=quote)}'
        
        if use_code_verifier:
            return url, state, challenge_code
            
        elif use_state:
            return url, state, None
            
        else:
            return url, None, None
    
    async def _access_token(self,
        grant_type: str,
        *,
        code: Optional[str] = None,
        code_verifier: Optional[str] = None,
        refresh_token: Optional[str] = None
    ) -> dict[str, Any]:
        client_id = self._client_id
        client_secret = self._client_secret
        args = {
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': grant_type,
            'redirect_uri': self._redirect_uri,
            'scope': self._scopes
        }
        if code is not None:
            args.update(code=code)
            if code_verifier is not None:
                args['code_verifier'] = code_verifier
            
        elif refresh_token is not None:
            args['refresh_token'] = refresh_token
        
        auth = base64.b64encode(f'{client_id}:{client_secret}'.encode('ascii')).decode('ascii')
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth}',
        }
        
        url = self._token_url
        data = urlencode(args, quote_via=quote)
        
        async with aiohttp.ClientSession() as client:
            async with client.post(url, headers=headers, data=data) as response:
                if response.status != 200:
                    raise OAuthError(await response.text())

                return await response.json()
    
    async def get_access_token(self,
        code: str,
        code_verifier: Optional[str] = None
    ) -> dict[str, Any]:
        return await self._access_token('authorization_code', code=code, code_verifier=code_verifier)
    
    async def refresh_access_token(self,
        refresh_token: str
    ) -> dict[str, Any]:
        return await self._access_token('refresh_token', refresh_token=refresh_token)
