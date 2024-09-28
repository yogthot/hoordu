import re
import dateutil.parser

from hoordu.dynamic import Dynamic
from hoordu.plugins import *
from hoordu.models.common import *
from hoordu.forms import *


NOTE_FORMAT = 'https://misskey.io/notes/{note_id}'
NOTE_REGEXP = [
    re.compile(r'^https?:\/\/misskey\.io\/notes\/(?P<note_id>[a-z0-9]+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE),
]
TIMELINE_REGEXP = re.compile(r'^https?:\/\/misskey\.io\/@(?P<user>[^\/]+)(?:\/(?P<type>[^\/]+)?)?(?:\?.*)?$', flags=re.IGNORECASE)

PAGE_LIMIT = 30


def str_base(number, base='0123456789abcdefghijklmnopqrstuvwxyz'):
   d, m = divmod(number, len(base))
   if d > 0:
      return str_base(d,base) + base[m]
   return base[m]


class Misskey(PluginBase):
    source = 'misskey'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('token', Input('token', [validators.required()])),
        )
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('method', ChoiceInput('method', [
                    ('notes', 'notes'),
                    ('renotes', 'renotes'),
                ], [validators.required()])),
            ('user', Input('screen name', [validators.required()]))
        )
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        for regexp in NOTE_REGEXP:
            match = regexp.match(url)
            if match:
                return match.group('note_id')
        
        match = TIMELINE_REGEXP.match(url)
        if match:
            user = match.group('user')
            method = match.group('type')
            
            method = 'notes'
            
            return Dynamic({
                'user': user,
                'method': method
            })
        
        return None
    
    def _check_renote(self, note):
        renote = note.get('renote')
        if renote is not None and note.text is None and note.cw is None and len(note.files) == 0:
            note = renote
        
        return note
    
    async def download(self, post_id, post_data=None):
        request = {
            'noteId': post_id,
            'i': self.config.token,
        }
        
        note = post_data
        if note is None:
            resp = await self.http.post('https://misskey.io/api/notes/show', json=request)
            resp.raise_for_status()
            note = Dynamic.from_json(await resp.text())
        
        note = self._check_renote(note)
        
        post = PostDetails()
        post.url = NOTE_FORMAT.format(note_id=note.id)
        post.comment = note.text if note.cw is None else f'{note.cw}\n{note.text}'
        post.post_time = dateutil.parser.isoparse(note.createdAt).replace(tzinfo=None)
        
        user = note.user.username if note.user.host is None else f'{note.user.username}@{note.user.host}'
        post.metadata = {'user': user}
        
        post.tags.append(TagDetails(TagCategory.artist, user))
        
        has_nsfw_file = any(f.isSensitive for f in note.files)
        if has_nsfw_file or note.cw is not None:
            post.tags.append(TagDetails(TagCategory.meta, 'nsfw'))
        
        hashtags = note.get('tags', [])
        for hashtag in hashtags:
            post.tags.append(TagDetails(TagCategory.general, hashtag))
        
        quoted = note.get('renote')
        if quoted is not None:
            post.related.append(NOTE_FORMAT.format(note_id=quoted.id))
        
        post.files = [
            FileDetails(
                url=f.url,
                order=i + 1
            )
            for i, f in enumerate(note.files)
        ]
        
        return post
    
    async def probe_query(self, query):
        request = {
            'username': query.user,
            'host': None,
            'i': self.config.token,
        }
        
        resp = await self.http.post('https://misskey.io/api/users/show', json=request)
        resp.raise_for_status()
        user = Dynamic.from_json(await resp.text())
        
        query.user_id = user.id
        
        related_urls = []
        if user.description is not None:
            # find urls from description
            pass
        
        thumb_url = user.avatarUrl
        
        return SearchDetails(
            identifier=f'{query.method}:{query.user_id}',
            hint=user.username,
            title=user.name if user.name is not None else user.username,
            description=user.description,
            thumbnail_url=thumb_url,
            related_urls=related_urls
        )
    
    def _validate_method(self, method, note):
        is_renote = False
        renote = note.get('renote')
        if renote is not None:
            is_renote = True
            note = renote
        
        media_list = note.get('files')
        
        has_files = (
            media_list is not None and
            len(media_list) > 0
        )
        
        if method == 'renotes':
            return has_files and is_renote
            
        elif method == 'notes':
            return has_files and not is_renote
    
    async def iterate_query(self, query, state=None, begin_at=None):
        if 'user_id' not in query:
            await self.probe_query(query)
        
        until_id = None
        if begin_at is not None:
            until_id = str_base(begin_at)
        
        while True:
            self.log.info('getting next page')
            request = {
                'userId': query.user_id,
                'limit': PAGE_LIMIT,
                'i': self.config.token,
                'excludeNsfw': False,
            }
            if until_id is not None:
                request['untilId'] = until_id
            
            resp = await self.http.post('https://misskey.io/api/users/notes', json=request)
            resp.raise_for_status()
            notes = Dynamic.from_json(await resp.text())
            
            if len(notes) == 0:
                return
            
            self.log.info(f'page date: {notes[0].createdAt}')
            
            for note in notes:
                sort_index = int(note.id, 36)
                if self._validate_method(query.method, note):
                    note = self._check_renote(note)
                    yield sort_index, note.id, note
                    until_id = note.id
                    
                else:
                    yield sort_index, None, None

Plugin = Misskey
