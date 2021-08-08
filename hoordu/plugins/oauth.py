import urllib3
from urllib.parse import urlencode, quote
from oauthlib.common import generate_token
import json

class OAuthError(BaseException):
    pass

class OAuth:
    def __init__(self, oauth_config):
        """
        The oauth_config parameter is a dictionary with the following string values:
        * client_id
        * client_secret
        * auth_url
        * token_url
        * callback_url
        * scopes (sent as-is as the scope parameter)
        """
        self.config = oauth_config
        self.http = urllib3.PoolManager()
    
    def auth_url(self, use_state=False):
        state = generate_token()
        args = {
            'response_type': 'code',
            'client_id': self.config['client_id'],
            'redirect_uri': self.config['callback_url'],
            'scope': self.config['scopes']
        }
        if use_state:
            args['state'] = state
        
        url = f"{self.config['auth_url']}?{urlencode(args, quote_via=quote)}"
        
        if not use_state:
            return url
            
        else:
            return url, state
    
    def _access_token(self, grant_type, *, code=None, refresh_token=None):
        args = {
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret'],
            'grant_type': grant_type,
            'redirect_uri': self.config['callback_url'],
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
            raise OAuthError(response.data)
        
        return json.loads(response.data)
    
    def get_access_token(self, code):
        return self._access_token('authorization_code', code=code)
    
    def refresh_access_token(self, refresh_token):
        return self._access_token('refresh_token', refresh_token=refresh_token) 
