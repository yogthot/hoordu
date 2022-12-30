from datetime import datetime
from enum import Enum, IntFlag, auto
import json
from typing import Any

from sqlalchemy import Table, Column, Integer, String, Text, LargeBinary, DateTime, ForeignKey, Index, func, inspect, select, insert
from sqlalchemy.orm import relationship, ColumnProperty, RelationshipProperty
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import async_object_session
from sqlalchemy.ext.compiler import compiles
from sqlalchemy_fulltext import FullText
from sqlalchemy_utils import ChoiceType

Base = declarative_base()

class MetadataHelper:
    def __init__(self, *args, **kwargs):
        pass
    
    def update_metadata(self, key: str, value: Any) -> bool:
        metadata = json.loads(self.metadata_) if self.metadata_ else {}
        if metadata.get(key) != value:
            metadata[key] = value
            self.metadata_ = json.dumps(metadata)
            return True

        else:
            return False

class FetchMixin:
    def __init__(self, *args, **kwargs):
        pass
    
    async def fetch(self, field: str | Column | RelationshipProperty) -> Base | list[Base] | None:
        session = async_object_session(self)
        
        if isinstance(field, InstrumentedAttribute):
            column = field
        else:
            column = getattr(self.__class__, field)
        
        property = column.property
        
        if not column.is_attribute or isinstance(property, ColumnProperty):
            return getattr(self, column.key)
        
        elif isinstance(property, RelationshipProperty):
            related_class = property.entity.entity
            
            conditions = []
            
            """
            # more simple approach with join
            statement = select(related_class).join(self.__class__, property.primaryjoin)
            
            for pk in inspect(self.__class__).primary_key:
                conditions.append(pk == getattr(self, pk.key))
            # /simple
            """
            
            # possible optimizations without join
            statement = select(related_class)
            for l, f in property.local_remote_pairs:
                if  l.table == self.__table__:
                    conditions.append(f == getattr(self, l.key))
            # /optimization
            
            if property.secondary is not None:
                statement = statement.join(property.secondary)
            
            statement = statement.where(*conditions)
            
            # get result
            result = await session.stream_scalars(statement)
            
            if property.uselist:
                return await result.all()
                
            else:
                return await result.one_or_none()


# convert collations
@compiles(String, 'postgresql')
def compile_unicode(element, compiler, **kw):
    if element.collation == 'NOCASE':
        element.collation = 'und-x-icu'
    return compiler.visit_unicode(element, **kw)
@compiles(Text, 'postgresql')
def compile_unicode(element, compiler, **kw):
    if element.collation == 'NOCASE':
        element.collation = 'und-x-icu'
    return compiler.visit_unicode(element, **kw)


class FlagProperty:
    def __init__(self, attr: str, flag):
        self.attr: str = attr
        self.flag = flag
    
    def __get__(self, obj: Base, cls) -> bool:
        return bool(getattr(obj, self.attr) & self.flag)
    
    def __set__(self, obj: Base, value: bool) -> None:
        setattr(obj, self.attr, (getattr(obj, self.attr) & ~self.flag) | (-bool(value) & self.flag))


post_tag = Table('post_tag', Base.metadata,
    Column('post_id', Integer, ForeignKey('post.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('tag_id', Integer, ForeignKey('tag.id', ondelete='CASCADE'), nullable=False)
)

class TagCategory(Enum):
    general = 1
    group = 2
    artist = 3
    copyright = 4
    character = 5
    # used for informational tags or personal reminders
    meta = 6

class TagFlags(IntFlag):
    none = 0
    favorite = auto()

class Tag(Base, FetchMixin):
    __tablename__ = 'tag'
    
    id = Column(Integer, primary_key=True)
    
    category = Column(ChoiceType(TagCategory, impl=Integer()), nullable=False)
    tag = Column(String(length=255, collation='NOCASE'), nullable=False)
    
    flags = Column(Integer, default=TagFlags.none, nullable=False)
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # flags
    favorite = FlagProperty('flags', TagFlags.favorite)
    
    __table_args__ = (
        Index('idx_tags', 'category', 'tag', unique=True),
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'flags' not in kwargs:
            self.flags = TagFlags.none
    
    def __str__(self):
        return '{}:{}'.format(self.category.name, self.tag)

class PostFlags(IntFlag):
    none = 0
    favorite = auto()
    hidden = auto()
    removed = auto() # if the post was deleted in the remote host

class PostType(Enum):
    set = 1 # bundle of unrelated files (or just a single file)
    collection = 2 # the files are related in some way
    blog = 3 # text with files in between (comment is formatted as json)
    # more types can be added as needed

class Post(Base, FetchMixin, MetadataHelper):
    __tablename__ = 'post'
    
    id = Column(Integer, primary_key=True)
    
    title = Column(Text(collation='NOCASE'))
    comment = Column(Text(collation='NOCASE'))
    
    type = Column(ChoiceType(PostType, impl=Integer()), nullable=False)
    flags = Column(Integer, default=PostFlags.none, nullable=False)
    
    metadata_ = Column('metadata', Text)
    post_time = Column(DateTime(timezone=False))
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    tags = relationship('Tag', secondary=post_tag)
    files = relationship('File', back_populates='local')
    
    # flags
    favorite = FlagProperty('flags', PostFlags.favorite)
    hidden = FlagProperty('flags', PostFlags.hidden)
    removed = FlagProperty('flags', PostFlags.removed)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'flags' not in kwargs:
            self.flags = PostFlags.none


class Source(Base, FetchMixin, MetadataHelper):
    __tablename__ = 'source'
    
    id = Column(Integer, primary_key=True)
    
    name = Column(String(length=255, collation='NOCASE'), nullable=False, index=True, unique=True)
    # rate limits, etc
    config = Column(Text)
    preferred_plugin_id = Column(Integer, ForeignKey('plugin.id', ondelete='SET NULL'), nullable=True)
    
    metadata_ = Column('metadata', Text)
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    subscriptions = relationship('Subscription', back_populates='source')
    preferred_plugin = relationship('Plugin', foreign_keys=[preferred_plugin_id])

class Plugin(Base, FetchMixin):
    __tablename__ = 'plugin'
    
    id = Column(Integer, primary_key=True)
    
    source_id = Column(Integer, ForeignKey('source.id'), nullable=False)
    
    name = Column(String(length=255, collation='NOCASE'), nullable=False, index=True, unique=True)
    version = Column(Integer, nullable=False)
    config = Column(Text)
    
    # references
    source = relationship('Source', foreign_keys=[source_id])

remote_post_tag = Table('remote_post_tag', Base.metadata,
    Column('post_id', Integer, ForeignKey('remote_post.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('tag_id', Integer, ForeignKey('remote_tag.id', ondelete='CASCADE'), nullable=False)
)

class RemoteTag(Base, FetchMixin, MetadataHelper):
    __tablename__ = 'remote_tag'
    
    id = Column(Integer, primary_key=True)
    
    source_id = Column(Integer, ForeignKey('source.id', ondelete='CASCADE'), nullable=False)
    
    category = Column(ChoiceType(TagCategory, impl=Integer()), nullable=False)
    tag = Column(String(length=255, collation='NOCASE'), nullable=False)
    
    metadata_ = Column('metadata', Text)
    
    flags = Column(Integer, default=TagFlags.none, nullable=False)
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    source = relationship('Source')
    translation = relationship('TagTranslation', back_populates='remote_tag')
    
    # flags
    favorite = FlagProperty('flags', TagFlags.favorite)
    
    __table_args__ = (
        Index('idx_remote_tags', 'source_id', 'category', 'tag', unique=True),
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'flags' not in kwargs:
            self.flags = TagFlags.none
    
    def __str__(self):
        return '{}:{}'.format(self.category.name, self.tag)

class RemotePost(Base, FetchMixin, MetadataHelper):
    __tablename__ = 'remote_post'
    
    id = Column(Integer, primary_key=True)
    
    source_id = Column(Integer, ForeignKey('source.id', ondelete='CASCADE'), nullable=False)
    
    # the minimum identifier for the post
    original_id = Column(Text, nullable=True)
    url = Column(Text)
    
    title = Column(Text(collation='NOCASE'))
    comment = Column(Text(collation='NOCASE'))
    
    type = Column(ChoiceType(PostType, impl=Integer()), nullable=False)
    flags = Column(Integer, default=PostFlags.none, nullable=False)
    
    metadata_ = Column('metadata', Text)
    post_time = Column(DateTime(timezone=False))
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    source = relationship('Source')
    tags = relationship('RemoteTag', secondary=remote_post_tag)
    files = relationship('File', back_populates='remote')
    related = relationship('Related', back_populates='related_to', foreign_keys='[Related.related_to_id]')
    
    # flags
    favorite = FlagProperty('flags', PostFlags.favorite)
    hidden = FlagProperty('flags', PostFlags.hidden)
    removed = FlagProperty('flags', PostFlags.removed)
    
    __table_args__ = (
        Index('idx_remote_posts', 'source_id', 'original_id', unique=True),
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'flags' not in kwargs:
            self.flags = PostFlags.none
        
        if 'type' not in kwargs:
            self.type = PostType.set
    
    async def add_tag(self, new_tag: RemoteTag) -> bool:
        if not hasattr(self, '_existing_tags'):
            self._existing_tags = {(t.category, t.tag) for t in await self.fetch('tags')}
        
        t = (new_tag.category, new_tag.tag)
        if t not in self._existing_tags:
            async_object_session(self).add(new_tag)
            self._existing_tags.add(t)
            return True
            
        else:
            return False
    
    async def add_related_url(self, url: str) -> bool:
        if not hasattr(self, '_existing_urls'):
            self._existing_urls = {r.url for r in await self.fetch('related')}
        
        if url not in self._existing_urls:
            async_object_session(self).add(Related(url=url))
            self._existing_urls.add(url)
            return True
            
        else:
            return False


class FileFlags(IntFlag):
    none = 0
    favorite = auto()
    hidden = auto()
    removed = auto() # if the file was removed in the remote host
    processed = auto() # if the file was already processed locally (accepted or rejected)
    present = auto() # if the file is present on the disk
    thumb_present = auto() # if the thumbnail is present on the disk

class File(Base, FetchMixin, MetadataHelper):
    __tablename__ = 'file'
    
    id = Column(Integer, primary_key=True)
    
    local_id = Column(Integer, ForeignKey('post.id', ondelete='SET NULL'))
    remote_id = Column(Integer, ForeignKey('remote_post.id', ondelete='SET NULL'))
    
    local_order = Column(Integer, default=0)
    remote_order = Column(Integer, default=0)
    
    # hash is md5 for compatibility
    hash = Column(LargeBinary(length=16), index=True)
    filename = Column(Text)
    mime = Column(String(length=255, collation='NOCASE'))
    ext = Column(String(length=20, collation='NOCASE'))
    thumb_ext = Column(String(length=20, collation='NOCASE'))
    
    metadata_ = Column('metadata', Text)
    
    flags = Column(Integer, default=FileFlags.none, nullable=False)
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    local = relationship('Post', back_populates='files')
    remote = relationship('RemotePost', back_populates='files')
    
    # flags
    favorite = FlagProperty('flags', FileFlags.favorite)
    hidden = FlagProperty('flags', FileFlags.hidden)
    removed = FlagProperty('flags', FileFlags.removed)
    processed = FlagProperty('flags', FileFlags.processed)
    present = FlagProperty('flags', FileFlags.present)
    thumb_present = FlagProperty('flags', FileFlags.thumb_present)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'flags' not in kwargs:
            self.flags = FileFlags.none


subscription_post = Table('feed', Base.metadata,
    Column('subscription_id', Integer, ForeignKey('subscription.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('remote_post_id', Integer, ForeignKey('remote_post.id', ondelete='CASCADE'), nullable=False)
)

class SubscriptionFlags(IntFlag):
    none = 0
    enabled = auto() # won't auto update if disabled

class Subscription(Base, FetchMixin):
    __tablename__ = 'subscription'
    
    id = Column(Integer, primary_key=True)
    
    source_id = Column(Integer, ForeignKey('source.id', ondelete='CASCADE'), nullable=False)
    plugin_id = Column(Integer, ForeignKey('plugin.id', ondelete='CASCADE'), nullable=True)
    
    repr = Column(Text, nullable=True)
    name = Column(Text, nullable=False)
    
    options = Column(Text)
    state = Column(Text)
    
    flags = Column(Integer, default=SubscriptionFlags.none, nullable=False)
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    source = relationship('Source', back_populates='subscriptions')
    plugin = relationship('Plugin')
    feed = relationship('RemotePost', secondary=subscription_post)
    
    # flags
    enabled = FlagProperty('flags', SubscriptionFlags.enabled)
    
    __table_args__ = (
        Index('idx_subscription', 'source_id', 'name', unique=True),
        Index('idx_subscription_repr', 'source_id', 'repr', unique=True),
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if 'flags' not in kwargs:
            self.flags = SubscriptionFlags.enabled
    
    async def add_post(self, post: RemotePost) -> bool:
        session = async_object_session(self)
        await session.flush()
        
        exists = await session.execute(select(Subscription) \
                .join(subscription_post) \
                .where(
                    Subscription.id == self.id,
                    subscription_post.c.remote_post_id == post.id
                ).exists().select())
        
        if exists.scalar():
            return False
        
        await session.execute(insert(subscription_post) \
                .values(subscription_id=self.id, remote_post_id=post.id))
        
        return True

class TagTranslation(Base, FetchMixin):
    __tablename__ = 'tag_translation'
    
    id = Column(Integer, ForeignKey('remote_tag.id', ondelete='CASCADE'), primary_key=True)
    # null local_tag_id -> ignore remote tag
    local_tag_id = Column(Integer, ForeignKey('tag.id', ondelete='CASCADE'))
    
    created_time = Column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)
    updated_time = Column(DateTime(timezone=False), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    remote_tag = relationship('RemoteTag', back_populates='translation')
    tag = relationship('Tag')

class Related(Base, FetchMixin):
    __tablename__ = 'related'
    
    id = Column(Integer, primary_key=True)
    # the post this url is related to
    related_to_id = Column(Integer, ForeignKey('remote_post.id', ondelete='CASCADE'))
    
    # the post the url corresponds to, in case it was downloaded
    remote_id = Column(Integer, ForeignKey('remote_post.id', ondelete='SET NULL'))
    
    url = Column(Text)
    
    related_to = relationship('RemotePost', back_populates='related', foreign_keys=[related_to_id])
    remote = relationship('RemotePost', foreign_keys=[remote_id])


