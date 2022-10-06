import urllib3
from urllib.parse import urlencode, quote
from oauthlib.common import generate_token
import json
import secrets
import hashlib
import base64

class OAuthError(Exception):
    pass

class OAuth:
    def __init__(self, oauth_config):
        """
        The oauth_config parameter is a dictionary with the following string values:
        * client_id
        * client_secret
        * auth_url
        * token_url
        * redirect_uri
        * scopes (sent as-is as the scope parameter)
        * code_challenge_method
        """
        self.config = oauth_config
        self.http = urllib3.PoolManager()
    
    def auth_url(self, use_state=False, use_code_verifier=False):
        if use_code_verifier:
            use_state = True
        
        state = generate_token()
        challenge_code = secrets.token_urlsafe(length)
        args = {
            'response_type': 'code',
            'client_id': self.config['client_id'],
            'redirect_uri': self.config['redirect_uri'],
            'scope': self.config['scopes']
        }
        if use_state:
            args['state'] = state
        
        if use_code_verifier:
            if self.config['code_challenge_method'] == 'plain':
                args['code_challenge'] = challenge_code
                
            else:
                # hash
                h = hashlib.sha256()
                h.update(challenge_code.encode('ascii'))
                digest = h.digest()
                # urlsafe_b64encode: which substitutes - instead of + and _ instead of / in the standard Base64 alphabet
                challenge = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
                args['code_challenge'] = challenge
        
        url = f"{self.config['auth_url']}?{urlencode(args, quote_via=quote)}"
        
        if use_code_verifier:
            return url, state, challenge_code
            
        elif use_state:
            return url, state
            
        else:
            return url
    
    def _access_token(self, grant_type, *, code=None, refresh_token=None):
        args = {
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret'],
            'grant_type': grant_type,
            'redirect_uri': self.config['redirect_uri'],
            'scope': self.config['scopes']
        }
        if code is not None:
            args.update(code=code)
            
        elif refresh_token is not None:
            args.update(refresh_token=refresh_token)
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        url = self.config['token_url']
        body = urlencode(args, quote_via=quote)
        response = self.http.request('POST', url, headers=headers, body=body)
        
        if response.status != 200:
            raise OAuthError(response.data.decode('utf-8'))
        
        return json.loads(response.data)
    
    def get_access_token(self, code):
        return self._access_token('authorization_code', code=code)
    
    def refresh_access_token(self, refresh_token):
        return self._access_token('refresh_token', refresh_token=refresh_token) 
