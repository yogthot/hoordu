from .common import *
from ..config import *
from ..models import *
from ..util import *

import logging
from lru import LRU

class APIError(Exception):
    pass

class SearchDetails:
    def __init__(self, hint=None, title=None, description=None, thumbnail_url=None, related_urls=set()):
        self.hint = hint
        self.title = title
        self.description = description
        self.thumbnail_url = thumbnail_url
        self.related_urls = set(related_urls)

class IteratorBase:
    def __init__(self, plugin, subscription=None, options=None):
        self.plugin = plugin
        self.session = plugin.session
        self.log = plugin.log
        self.subscription = subscription
        
        if self.subscription is not None:
            self.options = Dynamic.from_json(self.subscription.options)
            self.state = Dynamic.from_json(self.subscription.state)
        else:
            self.options = options
            self.state = Dynamic()
    
    def init(self):
        """
        Override this method to implement any startup IO task related
        to this specific subscription that doesn't need to execute
        on every fetch call.
        """
        
        pass
    
    def fetch(self, direction=FetchDirection.newer, n=None):
        """
        Try to get at least `n` newer or older posts from this search
        depending on the direction.
        Create a RemotePost entry and any associated Files for each post found,
        thumbnails should be downloaded, files are optional.
        Posts should always come ordered in the same way.
        This method may auto-commit by default.
        
        Returns a list of the new RemotePost objects.
        """
        
        raise NotImplementedError

class PluginBase:
    id = None # reserved
    name = None
    version = 0
    required_hoordu = '0.0.0'
    
    iterator = None
    
    @classmethod
    def config_form(cls):
        """
        Returns a form for the configuration of the values by the plugin.
        """
        
        raise NotImplementedError
    
    @classmethod
    def get_source(cls, session):
        return session.query(Source) \
                .filter(Source.name == cls.name) \
                .one_or_none()
    
    @classmethod
    def setup(cls, session, parameters=None):
        """
        Tries to initialize a plugin from existing configuration or new configuration
        passed in `parameters`.
        
        If the plugin initializes successfully, this should return a tuple of
        True and the plugin object.
        Otherwise, it should return a tuple of False and a form for any missing values
        required (e.g.: oauth tokens).
        """
        
        raise NotImplementedError
    
    @classmethod
    def update(cls, session):
        """
        Updates the database objects related to this plugin/source, if needed.
        """
        
        pass
    
    @classmethod
    def parse_url(cls, url):
        """
        Checks if an url can be downloaded by this plugin.
        
        Returns the remote id if the url corresponds to a single post,
        a Dynamic object that can be passed to search if the url
        corresponds to multiple posts, or None if this plugin can't
        download or create a search using this url.
        """
        
        return None
    
    def __init__(self, session):
        self.session = session
        self.source = self.get_source(session)
        
        self.config = Dynamic.from_json(self.source.config)
        
        log_file = template_format(session.hrd.settings.get('log_file'), name=self.name)
        self.log = get_logger(self.name, log_file, session.hrd.settings.get('log_level', logging.WARNING))
        
        # (category, tag) -> RemoteTag
        self._tag_cache = LRU(100)
    
    def _get_tag(self, category, tagstr):
        tag = self._tag_cache.get((category, tagstr))
        
        if tag is None:
            tag = self.session.query(RemoteTag) \
                    .filter(RemoteTag.source==self.source, RemoteTag.category==category, RemoteTag.tag==tagstr) \
                    .one_or_none()
            
            if tag is None:
                tag = RemoteTag(source=self.source, category=category, tag=tagstr)
                self.session.add(tag)
            
            self._tag_cache[category, tagstr] = tag
        
        return tag
        
    def download(self, id=None, remote_post=None, preview=False):
        """
        Creates or updates a RemotePost entry along with all the associated Files,
        and downloads all files and thumbnails that aren't present yet.
        
        If remote_post is passed, its original_id will be used and it will be
        updated in place.
        
        If preview is set to True, then only the thumbnails are downloaded.
        
        Returns the downloaded RemotePost object.
        """
        
        raise NotImplementedError
    
    def search_form(self):
        """
        Returns the form or a list of forms used for searches and subscriptions.
        (e.g.: user id, a search string, or advanced options available on the website)
        """
        
        return None
    
    def get_search_details(self, options):
        """
        Returns a SearchDetails object with extra details about the search that would
        be performed by this set of options (e.g.: user timeline).
        May return None if no specific information is found (e.g.: global searches).
        """
        
        return None
    
    def search(self, options):
        """
        Creates a temporary search for a given set of search options.
        
        Returns a post iterator object.
        """
        
        if self.iterator is None:
            raise NotImplementedError
        
        iterator = self.iterator(self, options=options)
        iterator.init()
        return iterator
    
    def subscription_repr(self, options):
        """
        Returns a simple representation of the subscription, used to find duplicate
        subscriptions.
        """
        
        raise NotImplementedError
    
    def subscribe(self, name, options=None, iterator=None):
        """
        Creates a Subscription entry for the given search options identified by the given name,
        should not get any posts from the post source.
        """
        
        if iterator is None:
            iterator = self.iterator(self, options=options)
        
        iterator.init()
        
        sub = Subscription(
            source=self.source,
            name=name,
            repr=self.subscription_repr(iterator.options),
            options=iterator.options.to_json(),
            state=iterator.state.to_json()
        )
        
        self.session.add(sub)
        self.session.flush()
        
        iterator.subscription = sub
        
        return iterator
    
    def create_iterator(self, subscription):
        """
        Gets the post iterator for a specific subscription.
        
        Returns a post iterator object.
        """
        
        if self.iterator is None:
            raise NotImplementedError
        
        iterator = self.iterator(self, subscription=subscription)
        iterator.init()
        return iterator

class ReverseSearchPluginBase(PluginBase):
    def search(self, options):
        """
        By extending ReverseSearchPluginBase, this method may be called with the following
        types of options objects: `{'url': 'https://...'}` and `{'path': '/home/...'}`.
        
        Reverse searching works the same as regular searching, but the RemotePosts returned
        need to include at least a thumbnail and related url.
        """
        
        if self.iterator is None:
            raise NotImplementedError
        
        iterator = self.iterator(self, options=options)
        iterator.init()
        return iterator
    
    def create_subscription(self, name, options=None, iterator=None):
        """
        This method is out of scope for reverse search plugins.
        """
        
        raise NotImplementedError
    
    def get_iterator(self, subscription):
        """
        This method is out of scope for reverse search plugins.
        """
        
        raise NotImplementedError
    
