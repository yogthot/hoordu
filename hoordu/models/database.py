from datetime import datetime
from enum import Enum, IntFlag, auto
import json
from typing import Any, Optional

from sqlalchemy import Table, Column, Integer, String, Text, LargeBinary, DateTime, Numeric, ForeignKey, Index, func, inspect, select, insert
from sqlalchemy.orm import relationship, ColumnProperty, RelationshipProperty, DeclarativeBase, Mapped, mapped_column
from sqlalchemy.orm.attributes import InstrumentedAttribute
from sqlalchemy.ext.asyncio import async_object_session, AsyncAttrs
from sqlalchemy.ext.compiler import compiles
from sqlalchemy_fulltext import FullText
from sqlalchemy_utils import ChoiceType

from .common import *

__all__ = [
    'TagFlags',
    'PostFlags',
    'FileFlags',
    'SubscriptionFlags',
    
    'Base',
    'Tag',
    'Post',
    'Source',
    'Plugin',
    'RemoteTag',
    'RemotePost',
    'File',
    'FeedEntry',
    'Subscription',
    'TagTranslation',
    'Related',
    
    'post_tag',
    'remote_post_tag',
]

class Base(AsyncAttrs, DeclarativeBase):
    pass

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

class TagFlags(IntFlag):
    none = 0
    favorite = auto()

class Tag(Base):
    __tablename__ = 'tag'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    category: Mapped[TagCategory] = mapped_column(ChoiceType(TagCategory, impl=Integer()), nullable=False)
    tag: Mapped[str] = mapped_column(String(length=255, collation='NOCASE'), nullable=False)
    
    flags: Mapped[TagFlags] = mapped_column(Integer, default=TagFlags.none, nullable=False)
    
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
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

class Post(Base, MetadataHelper):
    __tablename__ = 'post'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    title: Mapped[Optional[str]] = mapped_column(Text(collation='NOCASE'))
    comment: Mapped[Optional[str]] = mapped_column(Text(collation='NOCASE'))
    
    type: Mapped[PostType] = mapped_column(ChoiceType(PostType, impl=Integer()), nullable=False)
    flags: Mapped[int] = mapped_column(Integer, default=PostFlags.none, nullable=False)
    
    metadata_: Mapped[Optional[str]] = mapped_column('metadata', Text)
    post_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
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


class Source(Base, MetadataHelper):
    __tablename__ = 'source'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    name: Mapped[str] = mapped_column(String(length=255, collation='NOCASE'), nullable=False, index=True, unique=True)
    # rate limits, etc
    config: Mapped[Optional[str]] = mapped_column(Text)
    preferred_plugin_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('plugin.id', ondelete='SET NULL'), nullable=True)
    
    metadata_: Mapped[Optional[str]] = mapped_column('metadata', Text)
    
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    subscriptions: Mapped[list['Subscription']] = relationship('Subscription', back_populates='source')
    preferred_plugin: Mapped['Plugin'] = relationship('Plugin', foreign_keys=[preferred_plugin_id])

class Plugin(Base):
    __tablename__ = 'plugin'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey('source.id'), nullable=False)
    
    name: Mapped[str] = mapped_column(String(length=255, collation='NOCASE'), nullable=False, index=True, unique=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[Optional[str]] = mapped_column(Text)
    
    # references
    source: Mapped[Source] = relationship('Source', foreign_keys=[source_id])

remote_post_tag = Table('remote_post_tag', Base.metadata,
    Column('post_id', Integer, ForeignKey('remote_post.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('tag_id', Integer, ForeignKey('remote_tag.id', ondelete='CASCADE'), nullable=False)
)

class RemoteTag(Base, MetadataHelper):
    __tablename__ = 'remote_tag'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey('source.id'), nullable=False)
    
    category: Mapped[TagCategory] = mapped_column(ChoiceType(TagCategory, impl=Integer()), nullable=False)
    tag: Mapped[str] = mapped_column(String(length=255, collation='NOCASE'), nullable=False)
    
    metadata_: Mapped[Optional[str]] = mapped_column('metadata', Text)
    
    flags: Mapped[TagFlags] = mapped_column(Integer, default=TagFlags.none, nullable=False)
    
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    source: Mapped[Source] = relationship('Source')
    translation: Mapped['Tag'] = relationship('TagTranslation', back_populates='remote_tag')
    
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

class RemotePost(Base, MetadataHelper):
    __tablename__ = 'remote_post'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey('source.id'), nullable=False)
    
    # the minimum identifier for the post
    original_id: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text)
    
    title: Mapped[Optional[str]] = mapped_column(Text(collation='NOCASE'))
    comment: Mapped[Optional[str]] = mapped_column(Text(collation='NOCASE'))
    
    type: Mapped[PostType] = mapped_column(ChoiceType(PostType, impl=Integer()), nullable=False)
    flags: Mapped[int] = mapped_column(Integer, default=PostFlags.none, nullable=False)
    
    metadata_: Mapped[Optional[str]] = mapped_column('metadata', Text)
    post_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    source: Mapped[Source] = relationship('Source')
    tags: Mapped[list[RemoteTag]] = relationship('RemoteTag', secondary=remote_post_tag)
    files: Mapped[list['File']] = relationship('File', back_populates='remote')
    related: Mapped[list['Related']] = relationship('Related', back_populates='related_to', foreign_keys='[Related.related_to_id]')
    
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
            self._existing_tags = {(t.category, t.tag) for t in await self.awaitable_attrs.tags}
        
        t = (new_tag.category, new_tag.tag)
        if t not in self._existing_tags:
            self.tags.append(new_tag)
            self._existing_tags.add(t)
            return True
            
        else:
            return False
    
    async def add_related_url(self, url: str) -> bool:
        if not hasattr(self, '_existing_urls'):
            self._existing_urls = {r.url for r in await self.awaitable_attrs.related}
        
        if url not in self._existing_urls:
            self.related.append(Related(url=url))
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

class File(Base, MetadataHelper):
    __tablename__ = 'file'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    local_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('post.id', ondelete='SET NULL'))
    remote_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('remote_post.id', ondelete='SET NULL'))
    
    local_order: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    remote_order: Mapped[Optional[int]] = mapped_column(Integer, default=0)
    remote_identifier: Mapped[Optional[str]] = mapped_column(Text)
    
    # hash is md5 for compatibility
    hash: Mapped[Optional[bytes]] = mapped_column(LargeBinary(length=16), index=True)
    filename: Mapped[Optional[str]] = mapped_column(Text)
    mime: Mapped[Optional[str]] = mapped_column(String(length=255, collation='NOCASE'))
    ext: Mapped[Optional[str]] = mapped_column(String(length=20, collation='NOCASE'))
    thumb_ext: Mapped[Optional[str]] = mapped_column(String(length=20, collation='NOCASE'))
    
    metadata_: Mapped[Optional[str]] = mapped_column('metadata', Text)
    
    flags: Mapped[FileFlags] = mapped_column(Integer, default=FileFlags.none, nullable=False)
    
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    local: Mapped[Optional[Post]] = relationship('Post', back_populates='files')
    remote: Mapped[Optional[RemotePost]] = relationship('RemotePost', back_populates='files')
    
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


class FeedEntry(Base):
    __tablename__ = 'feed'
    subscription_id: Mapped[int] = mapped_column(Integer, ForeignKey('subscription.id', ondelete='CASCADE'), primary_key=True)
    remote_post_id: Mapped[int] = mapped_column(Integer, ForeignKey('remote_post.id', ondelete='CASCADE'), primary_key=True)
    
    sort_index: Mapped[int] = mapped_column(Numeric, nullable=False, default=0)
    
    # references
    post: Mapped[RemotePost] = relationship('RemotePost')
    subscription: Mapped['Subscription'] = relationship('Subscription', back_populates='feed')


class SubscriptionFlags(IntFlag):
    none = 0
    enabled = auto() # won't auto update if disabled

class Subscription(Base):
    __tablename__ = 'subscription'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey('source.id'), nullable=False)
    plugin_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('plugin.id', ondelete='SET NULL'), nullable=True)
    
    repr: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    
    options: Mapped[Optional[str]] = mapped_column(Text)
    state: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[str]] = mapped_column('metadata', Text)
    
    flags: Mapped[SubscriptionFlags] = mapped_column(Integer, default=SubscriptionFlags.none, nullable=False)
    
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    source: Mapped[Source] = relationship('Source', back_populates='subscriptions')
    plugin: Mapped[Optional[Plugin]] = relationship('Plugin')
    feed: Mapped[list[FeedEntry]] = relationship('FeedEntry', back_populates='subscription')
    
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
    
    async def add_post(self, post: RemotePost, sort_index=None) -> bool:
        if sort_index is None:
            try:
                sort_index = int(post.original_id)
            except (ValueError, TypeError):
                raise ValueError('sort_index cannot be None')
        
        session = async_object_session(self)
        if session is None:
            raise ValueError('SQLAlchemy session could not be found')
        
        await session.flush()
        
        exists = await session.execute(select(FeedEntry) \
                .where(
                    FeedEntry.subscription_id == self.id,
                    FeedEntry.remote_post_id == post.id
                ).exists().select())
        
        if exists.scalar():
            return False
        
        await session.execute(insert(FeedEntry) \
                .values(
                    subscription_id=self.id,
                    remote_post_id=post.id,
                    sort_index=sort_index
                ))
        
        return True

class TagTranslation(Base):
    __tablename__ = 'tag_translation'
    
    id: Mapped[int] = mapped_column(Integer, ForeignKey('remote_tag.id', ondelete='CASCADE'), primary_key=True)
    # null local_tag_id -> ignore remote tag
    local_tag_id: Mapped[int] = mapped_column(Integer, ForeignKey('tag.id', ondelete='CASCADE'))
    
    created_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # references
    remote_tag: Mapped[RemoteTag] = relationship('RemoteTag', back_populates='translation')
    tag: Mapped[Tag] = relationship('Tag')

class Related(Base):
    __tablename__ = 'related'
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # the post this url is related to
    related_to_id: Mapped[int] = mapped_column(Integer, ForeignKey('remote_post.id', ondelete='CASCADE'))
    
    # the post the url corresponds to, in case it was downloaded
    remote_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey('remote_post.id', ondelete='SET NULL'))
    
    url: Mapped[Optional[str]] = mapped_column(Text)
    
    related_to: Mapped[RemotePost] = relationship('RemotePost', back_populates='related', foreign_keys=[related_to_id])
    remote: Mapped[Optional[RemotePost]] = relationship('RemotePost', foreign_keys=[remote_id])


