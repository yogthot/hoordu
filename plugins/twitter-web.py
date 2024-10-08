import re
import dateutil.parser
import json

from hoordu.dynamic import Dynamic
from hoordu.models import *
from hoordu.plugins import *
from hoordu.forms import *


DOMAIN = 'x.com'
TWEET_DETAIL_URL = f'https://{DOMAIN}/i/api/graphql/Pn68XRZwyV9ClrAEmK8rrQ/TweetDetail'
USER_BY_ID = f'https://{DOMAIN}/i/api/graphql/8slyDObmnUzBOCu7kYZj_A/UserByRestId'
USER_BY_SCREENNAME = f'https://{DOMAIN}/i/api/graphql/qRednkZG-rn1P6b48NINmQ/UserByScreenName'
TIMELINE_URL = f'https://{DOMAIN}/i/api/graphql/nozbAzcOZmXPohAtWJJHZQ/UserTweetsAndReplies'
MEDIATIMELINE_URL = f'https://{DOMAIN}/i/api/graphql/Az0-KW6F-FyYTc2OJmvUhg/UserMedia'
LIKES_URL = f'https://{DOMAIN}/i/api/graphql/kgZtsNyE46T3JaEf2nF9vw/Likes'

TWEET_FORMAT = 'https://x.com/{user}/status/{tweet_id}'
TWEET_REGEXP = [
    re.compile(r'^https?:\/\/(x|twitter)\.com\/(?P<user>[^\/]+)\/status\/(?P<tweet_id>\d+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE),
    re.compile(r'^https?:\/\/(x|twitter)\.com\/i\/web\/status\/(?P<tweet_id>\d+)(?:\/.*)?(?:\?.*)?$', flags=re.IGNORECASE)
]
TIMELINE_REGEXP = re.compile(r'^https?:\/\/(x|twitter)\.com\/(?P<user>[^\/]+)(?:\/(?P<type>[^\/]+)?)?(?:\?.*)?$', flags=re.IGNORECASE)

PROFILE_IMAGE_REGEXP = re.compile(r'^(?P<base>.+_)(?P<size>[^\.]+)(?P<ext>.+)$')

NEW_MEDIA_URL = '{base_url}?format={ext}&name={size}'
OLD_MEDIA_URL = '{base_url}.{ext}:{size}'
MEDIA_URL = NEW_MEDIA_URL

# these options are appended to the end of image urls when downloading
THUMB_SIZE = 'small'
ORIG_SIZE = 'orig'
PROFILE_THUMB_SIZE = '200x200'

PAGE_LIMIT = 40


class Twitter(PluginBase):
    source = 'twitter'
    
    @classmethod
    def config_form(cls):
        return Form(f'{cls.source} config',
            ('csrf', Input('csrf', [validators.required()])),
            ('bearer_token', Input('bearer token', [validators.required()])),
            ('auth_token', Input('auth token', [validators.required()])),
        )
    
    @classmethod
    def search_form(cls):
        return Form(f'{cls.source} search',
            ('method', ChoiceInput('method', [
                    ('tweets', 'tweets'),
                    ('retweets', 'retweets'),
                    ('likes', 'likes')
                ], [validators.required()])),
            ('user', Input('screen name', [validators.required()]))
        )
    
    @classmethod
    async def parse_url(cls, url):
        if url.isdigit():
            return url
        
        for regexp in TWEET_REGEXP:
            match = regexp.match(url)
            if match:
                return match.group('tweet_id')
        
        match = TIMELINE_REGEXP.match(url)
        if match:
            user = match.group('user')
            method = match.group('type')
            
            #if method != 'likes':
            #    method = 'tweets'
            method = 'tweets'
            
            return Dynamic({
                'user': user,
                'method': method
            })
        
        return None
    
    async def init(self):
        self.http.headers.update({
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://twitter.com/',
            'authorization': f'Bearer {self.config.bearer_token}',
            'x-twitter-auth-type': 'OAuth2Session',
            'x-csrf-token': self.config.csrf,
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
        })
        self.http.cookie_jar.update_cookies({
            'ct0': self.config.csrf,
            'auth_token': self.config.auth_token,
        })
    
    
    async def _get_tweet(self, tweet_id):
        variables = {
            'focalTweetId': str(tweet_id),
            'with_rux_injections': False,
            'includePromotedContent': True,
            'withCommunity': True,
            'withQuickPromoteEligibilityTweetFields': True,
            'withBirdwatchNotes': True,
            'withVoice': True,
            'withV2Timeline': True,
        }
        features = {
            'rweb_lists_timeline_redesign_enabled': True,
            'responsive_web_graphql_exclude_directive_enabled': True,
            'verified_phone_label_enabled': False,
            'creator_subscriptions_tweet_preview_api_enabled': True,
            'responsive_web_graphql_timeline_navigation_enabled': True,
            'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
            'tweetypie_unmention_optimization_enabled': True,
            'responsive_web_edit_tweet_api_enabled': True,
            'graphql_is_translatable_rweb_tweet_is_translatable_enabled': True,
            'view_counts_everywhere_api_enabled': True,
            'longform_notetweets_consumption_enabled': True,
            'tweet_awards_web_tipping_enabled': False,
            'freedom_of_speech_not_reach_fetch_enabled': True,
            'standardized_nudges_misinfo': True,
            'tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled': False,
            'longform_notetweets_rich_text_read_enabled': True,
            'longform_notetweets_inline_media_enabled': False,
            'responsive_web_enhance_cards_enabled': False,
        }
        params = {
            'variables': json.dumps(variables),
            'features': json.dumps(features),
        }
        
        async with self.http.get(TWEET_DETAIL_URL, params=params) as resp:
            body = Dynamic.from_json(await resp.text())
        
        instructions = body.data.threaded_conversation_with_injections_v2.instructions
        for inst in instructions:
            if inst.type == 'TimelineAddEntries':
                entries = inst.entries
                for entry in entries:
                    if entry.content.entryType == 'TimelineTimelineItem' \
                            and entry.content.itemContent.itemType == 'TimelineTweet':
                        tweet = entry.content.itemContent.tweet_results.result
                        if 'tweet' in tweet: tweet = tweet.tweet
                        if tweet.get('__typename') == 'TweetTombstone': continue
                        if tweet.rest_id == tweet_id:
                            return tweet
        
        raise APIError('fixme')
    
    async def download(self, post_id, post_data=None):
        if post_data is None:
            post_data = await self._get_tweet(post_id)
            
            #retweeted = post_data.legacy.get('retweeted_status_result')
            #if retweeted is not None:
            #    tweet = retweeted.result
            #    if 'tweet' in tweet: tweet = tweet.tweet
        
        author = post_data.core.user_results.result
        
        user = author.legacy.screen_name
        user_id = author.rest_id
        text = post_data.legacy.full_text
        post_time = dateutil.parser.parse(post_data.legacy.created_at)
        
        post = PostDetails()
        
        post.url = TWEET_FORMAT.format(user=user, tweet_id=post_id)
        post.comment = text
        post.type = PostType.set
        post.post_time = post_time
        post.metadata = {'user': user}
        
        post.tags.append(TagDetails(
            category=TagCategory.artist,
            tag=user_id,
            metadata={'user': user}
        ))
        
        if post_data.legacy.possibly_sensitive:
            post.tags.append(TagDetails(
                category=TagCategory.meta,
                tag='nsfw'
            ))
        
        hashtags = post_data.legacy.get_path('entities', 'hashtags')
        if hashtags is not None:
            for hashtag in hashtags:
                post.tags.append(TagDetails(
                    category=TagCategory.general,
                    tag=hashtag.text
                ))
        
        def add_related_tweet(related):
            if 'tweet' in related: related = related.tweet
            if related.get('__typename') == 'TweetTombstone':
                return
            
            related_id = related.rest_id
            related_user = related.core.user_results.result
            url = TWEET_FORMAT.format(user=related_user.legacy.screen_name, tweet_id=related_id)
            post.related.append(url)
        
        quoted = post_data.get_path('quoted_status_result', 'result')
        if quoted is not None:
            add_related_tweet(quoted)
        
        urls = post_data.legacy.get_path('entities', 'urls')
        if urls is not None:
            for url in urls:
                # hopefully no t.co bullshit here
                post.related.append(url.expanded_url)
        
        
        media_list = post_data.legacy.get_path('extended_entities', 'media')
        if media_list is not None:
            for order, media in enumerate(media_list):
                availability = media.get_path('ext_media_availability', 'status')
                if availability == 'Unavailable':
                    reason = media.get_path('ext_media_availability', 'reason')
                    self.log.warning(f'file is unavailable: {order}; reason: {reason}')
                    continue
                
                ##
                if media.type == 'photo':
                    base_url, ext = media.media_url_https.rsplit('.', 1)
                    filename = '{}.{}'.format(base_url.rsplit('/', 1)[-1], ext)
                    
                    post.files.append(FileDetails(
                        url=MEDIA_URL.format(base_url=base_url, ext=ext, size=ORIG_SIZE),
                        order=order,
                        filename=filename
                    ))
                    
                elif media.type in ('video', 'animated_gif'):
                    base_url, ext = media.media_url_https.rsplit('.', 1)
                    
                    variants = media.get_path('video_info', 'variants')
                    if variants is None:
                        variants = []
                    
                    best_variant = max(
                        [v for v in variants if 'bitrate' in v],
                        key=lambda v: v['bitrate'],
                        default=None
                    )
                    
                    if best_variant is None:
                        raise NotImplementedError(f'unable to download video: {variants}')
                    
                    post.files.append(FileDetails(
                        url=best_variant['url'],
                        order=order
                    ))
                    
                else:
                    raise NotImplementedError(f'unknown media type: {media.type}')
        
        return post
    
    async def _get_user(self, user_id=None, username=None):
        variables = {
            'withSafetyModeUserFields': True,
        }
        features = {
            'hidden_profile_likes_enabled': False,
            'responsive_web_graphql_exclude_directive_enabled': True,
            'verified_phone_label_enabled': False,
            'highlights_tweets_tab_ui_enabled': True,
            'creator_subscriptions_tweet_preview_api_enabled': True,
            'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
            'responsive_web_graphql_timeline_navigation_enabled': True,
        }
        
        if user_id is not None:
            url = USER_BY_ID
            variables['userId'] = user_id
            
        elif username is not None:
            url = USER_BY_SCREENNAME
            variables['screen_name'] = username
            features['subscriptions_verification_info_verified_since_enabled'] = True
            
        else:
            raise Exception('unreachable')
        
        params = {
            'variables': json.dumps(variables),
            'features': json.dumps(features),
        }
        
        async with self.http.get(url, params=params) as resp:
            body = Dynamic.from_json(await resp.text())
        
        user = body.get_path('data', 'user', 'result')
        
        if user is None:
            raise APIError('This account does not exist')
        
        if user['__typename'] == 'UserUnavailable':
            raise APIError(f'{user.reason}: {user.message}')
        
        return user
    
    async def probe_query(self, query):
        if query.method == 'likes':
            self.log.warning('likes are unreliable')
        
        user_id = query.get('user_id')
        kwargs = {'user_id': user_id} if user_id else {'username': query.user} 
        
        user = await self._get_user(**kwargs)
        query.user_id = user.rest_id
        
        urls = user.legacy.get_path('entities', 'url', 'urls') or []
        description_urls = user.legacy.get_path('entities', 'description', 'urls') or []
        related_urls = {u.expanded_url for u in urls + description_urls}
        
        thumb_url = user.legacy.profile_image_url_https
        match = PROFILE_IMAGE_REGEXP.match(thumb_url)
        if match:
            thumb_url = match.group('base') + PROFILE_THUMB_SIZE + match.group('ext')
        
        return SearchDetails(
            identifier=f'{query.method}:{query.user_id}',
            hint=user.legacy.screen_name,
            title=user.legacy.name,
            description=user.legacy.description,
            thumbnail_url=thumb_url,
            related_urls=list(related_urls)
        )
    
    def _validate_tweet(self, query, tweet):
        if tweet is None:
            return False, tweet, 0
        
        if 'tweet' in tweet: tweet = tweet.tweet
        if tweet.get('__typename') == 'TweetTombstone':
            return False, tweet, 0
        
        # check the user
        try:
            tweet_user_id = tweet.core.user_results.result.rest_id
            is_same_user = (tweet_user_id == query.user_id)
        except AttributeError:
            self.log.warning(tweet)
            is_same_user = False
            
        sort_index = int(tweet.rest_id)
        
        is_retweet = False
        retweeted = tweet.legacy.get('retweeted_status_result')
        if retweeted is not None:
            is_retweet = True
            tweet = retweeted.result
            if 'tweet' in tweet: tweet = tweet.tweet
            if tweet.get('__typename') == 'TweetTombstone':
                return False, tweet, 0
        
        media_list = tweet.legacy.get_path('extended_entities', 'media')
        urls = tweet.legacy.get_path('entities', 'urls')
        
        has_media = ((
            media_list is not None and
            len(media_list) > 0
        ) or (
            urls is not None and
            len(urls) > 0
        ))
        
        can_download = False
        if query.method == 'retweets':
            can_download = has_media and is_retweet
            
        elif query.method == 'tweets':
            can_download = has_media and not is_retweet and is_same_user
            
        elif query.method == 'likes':
            can_download = has_media
        
        return can_download, tweet, sort_index
    
    async def iterate_query(self, query, state, begin_at=None):
        if 'user_id' not in query:
            await self.probe_query(query)
        
        cursor = None
        while True:
            self.log.info('getting next page')
            is_media = False
            if query.method == 'tweets':
                # TODO when changing backt to _get_timeline, need to handle pinned tweets
                #body = await self.api._get_timeline(self.options.user_id, count=PAGE_LIMIT, cursor=cursor)
                body = await self._get_media_timeline(query.user_id, count=PAGE_LIMIT, cursor=cursor)
            elif query.method == 'retweets':
                body = await self._get_timeline(query.user_id, count=PAGE_LIMIT, cursor=cursor)
            elif query.method == 'likes':
                # likes are just unreliable
                body = await self._get_likes(query.user_id, count=PAGE_LIMIT, cursor=cursor)
            else:
                raise Exception('unreachable')
            
            try:
                instructions = body.data.user.result.timeline_v2.timeline.instructions
            except:
                self.log.warning(body)
                
                #try:
                # try to handle rate limit errors
                # {'errors': [{'code': 88, 'message': 'Rate limit exceeded.'}]}
                #if 'errors' in body and len(body.errors) == 1:
                raise APIError(body.errors[0].message)
                #except: pass
            
            for inst in instructions:
                if inst.type == 'TimelinePinEntry':
                    entry = inst.entry
                    if entry.content.entryType == 'TimelineTimelineItem':
                        tweet = entry.content.itemContent.tweet_results.get('result')
                        can_download, tweet, sort_index = self._validate_tweet(query, tweet)
                        if can_download:
                            #if self._validate_user(query, tweet):
                            #    yield True, tweet.rest_id, tweet
                            pass
                    
                elif inst.type == 'TimelineAddEntries':
                    for entry in inst.entries:
                        entryType = entry.entryId.rsplit('-', 1)[0]
                        if entryType == 'tweet':
                            tweet = entry.content.itemContent.tweet_results.get('result')
                            can_download, tweet, sort_index = self._validate_tweet(query, tweet)
                            if can_download:
                                sort_index = entry.sortIndex if query.method == 'likes' else sort_index
                                yield sort_index, tweet.rest_id, tweet
                            
                        elif entryType == 'profile-conversation':
                            for item in entry.content['items']:
                                tweet = content = item.item.itemContent.tweet_results.result
                                can_download, tweet, sort_index = self._validate_tweet(query, tweet)
                                if can_download:
                                    yield sort_index, tweet.rest_id, tweet
                            
                        elif entryType == 'cursor-bottom':
                            cursor = entry.content.value
                            
                        elif entryType in ('who-to-follow', 'cursor-top'):
                            # nop
                            pass
                            
                        elif entryType.startswith('promoted-tweet'):
                            pass
                            
                        elif entryType.startswith('profile-grid'):
                            for it in entry.content['items']:
                                item = it.item.itemContent
                                if item.itemType == 'TimelineTweet':
                                    tweet = item.tweet_results.get('result')
                                    can_download, tweet, sort_index = self._validate_tweet(query, tweet)
                                    if can_download:
                                        yield sort_index, tweet.rest_id, tweet
                                    
                                else:
                                    raise NotImplementedError(f'unknown item type: {entry.entryId}')
                            
                        else:
                            raise NotImplementedError(f'unknown entry type: {entry.entryId}')
                    
                    if len(inst.entries) == 2 and not is_media:
                        # hopefully this is the last page?
                        # only 2 cursor entries...
                        return
                    
                elif inst.type == 'TimelineAddToModule':
                    for it in inst.moduleItems:
                        item = it.item.itemContent
                        if item.itemType == 'TimelineTweet':
                            try:
                                tweet = item.tweet_results.result
                            except:
                                self.log.warning(item)
                                raise
                            can_download, tweet, sort_index = self._validate_tweet(query, tweet)
                            if can_download:
                                is_media = True
                                yield sort_index, tweet.rest_id, tweet
                            
                        else:
                            raise NotImplementedError(f'unknown item type: {item.itemType}')
                    
                elif inst.type in ('TimelineClearCache', 'TimelineTimelineModule', 'TimelineTerminateTimeline'):
                    # nop
                    pass
                    
                else:
                    raise NotImplementedError(f'unknown instruction type: {inst.type}')
    
    async def _get_timeline(self, user_id, count=PAGE_LIMIT, cursor=None):
        variables = {
            'userId': user_id,
            'count': count,
            'includePromotedContent': True,
            'withCommunity': True,
            'withVoice': True,
            'withV2Timeline': True
        }
        features = {
            'responsive_web_graphql_exclude_directive_enabled': True,
            'verified_phone_label_enabled': False,
            'responsive_web_home_pinned_timelines_enabled': True,
            'creator_subscriptions_tweet_preview_api_enabled': True,
            'responsive_web_graphql_timeline_navigation_enabled': True,
            'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
            'c9s_tweet_anatomy_moderator_badge_enabled': True,
            'tweetypie_unmention_optimization_enabled': True,
            'responsive_web_edit_tweet_api_enabled': True,
            'graphql_is_translatable_rweb_tweet_is_translatable_enabled': True,
            'view_counts_everywhere_api_enabled': True,
            'longform_notetweets_consumption_enabled': True,
            'responsive_web_twitter_article_tweet_consumption_enabled': False,
            'tweet_awards_web_tipping_enabled': False,
            'freedom_of_speech_not_reach_fetch_enabled': True,
            'standardized_nudges_misinfo': True,
            'tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled': True,
            'longform_notetweets_rich_text_read_enabled': True,
            'longform_notetweets_inline_media_enabled': True,
            'responsive_web_media_download_video_enabled': False,
            'responsive_web_enhance_cards_enabled': False,
        }
        
        if cursor is not None:
            variables['cursor'] = cursor
        
        params = {
            'variables': json.dumps(variables),
            'features': json.dumps(features),
        }
        
        async with self.http.get(TIMELINE_URL, params=params) as resp:
            text = await resp.text()
            try:
                return Dynamic.from_json(text)
            except:
                raise APIError(text)
    
    async def _get_media_timeline(self, user_id, count=PAGE_LIMIT, cursor=None):
        variables = {
            'userId': user_id,
            'count': count,
            'includePromotedContent': False,
            'withClientEventToken': False,
            'withBirdwatchNotes': False,
            'withVoice': True,
            'withV2Timeline': True,
        }
        features = {
            'rweb_lists_timeline_redesign_enabled': True,
            'responsive_web_graphql_exclude_directive_enabled': True,
            'verified_phone_label_enabled': False,
            'creator_subscriptions_tweet_preview_api_enabled': True,
            'responsive_web_graphql_timeline_navigation_enabled': True,
            'responsive_web_graphql_skip_user_profile_image_extensions_enabled': False,
            'tweetypie_unmention_optimization_enabled': True,
            'responsive_web_edit_tweet_api_enabled': True,
            'graphql_is_translatable_rweb_tweet_is_translatable_enabled': True,
            'view_counts_everywhere_api_enabled': True,
            'longform_notetweets_consumption_enabled': True,
            'responsive_web_twitter_article_tweet_consumption_enabled': False,
            'tweet_awards_web_tipping_enabled': False,
            'freedom_of_speech_not_reach_fetch_enabled': True,
            'standardized_nudges_misinfo': True,
            'tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled': True,
            'longform_notetweets_rich_text_read_enabled': True,
            'longform_notetweets_inline_media_enabled': True,
            'responsive_web_media_download_video_enabled': False,
            'responsive_web_enhance_cards_enabled': False,
        }
        fieldToggles = {
            'withArticleRichContentState': False,
        }
        
        if cursor is not None:
            variables['cursor'] = cursor
        
        params = {
            'variables': json.dumps(variables),
            'features': json.dumps(features),
            'fieldToggles': json.dumps(fieldToggles),
        }
        
        async with self.http.get(MEDIATIMELINE_URL, params=params) as resp:
            text = await resp.text()
            try:
                return Dynamic.from_json(text)
            except:
                raise APIError(text)
    
    async def _get_likes(self, user_id, count=PAGE_LIMIT, cursor=None):
        variables = {
            'userId': user_id,
            'count': count,
            'includePromotedContent': False,
            'withClientEventToken': False,
            'withBirdwatchNotes': False,
            'withVoice': True,
            'withV2Timeline': True,
        }
        features = {
            'rweb_lists_timeline_redesign_enabled':True,
            'responsive_web_graphql_exclude_directive_enabled':True,
            'verified_phone_label_enabled':False,
            'creator_subscriptions_tweet_preview_api_enabled':True,
            'responsive_web_graphql_timeline_navigation_enabled':True,
            'responsive_web_graphql_skip_user_profile_image_extensions_enabled':False,
            'tweetypie_unmention_optimization_enabled':True,
            'responsive_web_edit_tweet_api_enabled':True,
            'graphql_is_translatable_rweb_tweet_is_translatable_enabled':True,
            'view_counts_everywhere_api_enabled':True,
            'longform_notetweets_consumption_enabled':True,
            'responsive_web_twitter_article_tweet_consumption_enabled':False,
            'tweet_awards_web_tipping_enabled':False,
            'freedom_of_speech_not_reach_fetch_enabled':True,
            'standardized_nudges_misinfo':True,
            'tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled':True,
            'longform_notetweets_rich_text_read_enabled':True,
            'longform_notetweets_inline_media_enabled':True,
            'responsive_web_media_download_video_enabled':False,
            'responsive_web_enhance_cards_enabled':False
        }
        fieldToggles = {
            'withArticleRichContentState': False,
        }
        
        if cursor is not None:
            variables['cursor'] = cursor
        
        params = {
            'variables': json.dumps(variables),
            'features': json.dumps(features),
            'fieldToggles': json.dumps(fieldToggles),
        }
        
        async with self.http.get(LIKES_URL, params=params) as resp:
            return Dynamic.from_json(await resp.text())

Plugin = Twitter

