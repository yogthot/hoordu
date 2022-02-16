#!/usr/bin/env python3

import sys
from pathlib import Path
import importlib.util
import traceback
from getpass import getpass

import hoordu
from hoordu.models import *
from hoordu.plugins import FetchDirection
from hoordu.forms import *

from sqlalchemy.exc import IntegrityError

def fail(error):
    print(f'error: {error}', file=sys.stderr)
    sys.exit(1)

def usage():
    print(f'python {sys.argv[0]} <command> [command arguments]')
    print(f'python {sys.argv[0]} <url> [<url>...]')
    print("")
    print("global arguments:")
    print("    -p <plugin id>, --plugin <plugin id>")
    print("        selects a plugin (this affects subsequent arguments)")
    print("")
    print("    -s <source>, --source <source>")
    print("        selects a source (this affects subsequent arguments)")
    print("")
    print("    -d, --disabled")
    print("        list: lists disabled subscriptions instead")
    print("")
    print("available commands:")
    print("    setup")
    print("        sets up a plugin (requires --plugin)")
    print("")
    print("    list")
    print("        lists all enabled subscriptions for a source (requires --source)")
    print("")
    print("    update [[<source>:]<subscription name>]")
    print("        gets all new posts for a subscription")
    print("        ':' won't be used as a separator if a source is specified")
    print("")
    print("        gets all new posts for all subscriptions if")
    print("        no subscription is specified (requires --plugin or --source)")
    print("")
    print("    fetch [<source>:]<subscription name> <n>")
    print("        gets 'n' older posts for a subscription")
    print("")
    print("    rfetch [<source>:]<subscription name> <n>")
    print("        gets 'n' newer posts from a subscription")
    print("")
    print("    related <url> <related url> [<related url>...]")
    print("        downloads 'url' and all 'related url's")
    print("")
    print("alternative usage:")
    print("    when passed a list of urls, this command will attempt to download")
    print("    all of them, unless one of them corresponds to a list of posts")

def parse_sub_name(arg, args):
    if args.source is None and ':' in arg:
        args.source, args.subscription = arg.split(':')
        
    else:
        args.subscription = arg

def parse_url(hrd, arg, args):
    id, options = hrd.parse_url(arg, plugin_id=args.plugin_id)
    if id is None:
        if plugin_id is None:
            fail(f'unable to download url: {arg}')
            
        else:
            fail(f'plugin \'{plugin_id}\' can\'t to download url: {arg}')
    
    return id, options

def parse_args(hrd):
    # parse arguments
    args = hoordu.Dynamic()
    args.source = None
    args.plugin_id = None
    args.command = None
    args.urls = []
    args.subscription = None
    args.num_posts = None
    args.disabled = False
    
    argi = 1
    sargi = 0 # sub argument count
    while argi < argc:
        arg = sys.argv[argi]
        argi += 1
        
        # global commands
        if arg == '-h' or arg == '--help':
            usage()
            sys.exit(0)
        
        elif arg == '-p' or arg == '--plugin':
            args.plugin_id = sys.argv[argi]
            argi += 1
            
        elif arg == '-s' or arg == '--source':
            args.source = sys.argv[argi]
            argi += 1
            
        elif arg == '-d' or arg == '--disabled':
            args.disabled = True
            
        elif args.command is None:
            # pick command, or append to list or urls
            if arg in ('setup', 'list', 'enable', 'disable', 'update', 'fetch', 'rfetch', 'related'):
                args.command = arg
                sargi = 0
                
            else:
                args.urls.append(parse_url(hrd, arg, args))
            
        else:
            # sub-command arguments
            if args.command in ('enable', 'disable', 'update') and sargi < 1:
                parse_sub_name(arg, args)
                sargi += 1
                
            elif args.command in ('fetch', 'rfetch') and sargi < 2:
                if sargi == 0:
                    parse_sub_name(arg, args)
                    
                else:
                    args.num_posts = int(arg)
                
                sargi += 1
                
            elif args.command in ('related',) and sargi < 2:
                args.urls.append(parse_url(hrd, arg, args))
                sargi += 1
                
            else:
                fail(f'unknown argument: {arg}')
    
    # verify arguments
    urlc = len(args.urls)
    if urlc >= 2:
        for id, options in args.urls:
            if isinstance(options, hoordu.Dynamic):
                fail('can only process one search url at a time')
    
    if args.command == 'related' and urlc <= 1:
        fail('the related sub-command requires at least 2 urls')
    
    if args.command in ('list',) and args.source is None:
        fail(f'{args.command} sub-command requires a source to be specified')
    
    if args.command in ('setup',) and args.plugin_id is None:
        fail(f'{args.command} sub-command requires a plugin to be specified')
    
    if args.command in ('enable', 'disable', 'fetch', 'rfetch') and args.subscription is None:
        fail(f'{args.command} sub-command requires a subscription to be specified')
    
    if args.command == 'update' and args.subscription is None and args.plugin_id is None and args.source is None:
        fail(f'update sub-command requires a plugin, a source or a subscription to be specified')
    
    return args

# plugin setup
def _cli_form(form):
    form.clear()
    
    print(f'== {form.label} ===========')
    for entry in form.entries:
        if isinstance(entry, Section):
            print(f'-- {entry.label} ----------')
            print()
            execute_form(entry)
            print('--------------' + '-' * len(entry.label))
        
        else:
            if entry.errors:
                for error in entry.errors:
                    print(f'error: {error}')
                
            if isinstance(entry, Label):
                print(entry.label)
                print()
                
            elif isinstance(entry, PasswordInput):
                value = getpass('{entry.label}: ')
                if value: entry.value = value
                
            elif isinstance(entry, ChoiceInput):
                print(f'{entry.label}:')
                for k, v in entry.choices:
                    print(f'    {k}: {v}')
                value = input('pick a choice: ')
                if value: entry.value = value
                
            elif isinstance(entry, Input):
                value = input(f'{entry.label}: ')
                if value: entry.value = value
                
            else:
                print()

def cli_form(form):
    _cli_form(form)
    while not form.validate():
        _cli_form(form)

# this should be the general approach to setting up a plugin
def setup_plugin(hrd, id):
    form = None
    
    while True:
        parameters = None
        if form is not None:
            parameters = form.value
        
        # attempt to init
        success, form = hrd.setup_plugin(id, parameters=parameters)
        
        if success:
            return True
        
        elif form is not None:
            # if not successful but something else was returned
            # then attempt to ask the user for input
            
            cli_form(form)
        
        else:
            fail('something went wrong with the plugin setup')


def safe_fetch(session, iterator):
    posts = {}
    while True:
        try:
            for remote_post in iterator:
                posts[remote_post.id] = remote_post
            
            return posts
            
        except Exception:
            traceback.print_exc()
            if iterator.subscription is not None:
                subscription = iterator.subscription
                name = subscription.name
                print(f'subscription "{name}" ran into an error')
                print('y = retry; d = rollback, ignore and disable subscription; n = just rollback and ignore')
                v = input('do you want to retry? (Ynd) ').lower()
                if not v: v = 'y'
                if v == 'y':
                    # make sure we retry from a valid db state
                    session.flush()
                    continue
                    
                elif v == 'd':
                    session.rollback()
                    
                    subscription.enabled = False
                    session.add(subscription)
                    session.commit()
                    return
                    
                else:
                    session.rollback()
                    return

def process_sub(session, plugin_id, options):
    plugin = session.plugin(plugin_id)
    
    details = plugin.get_search_details(options)
    
    if details is not None:
        description = details.description.replace('\n', '\n    ')
        related = '\n    '.join(details.related_urls)
        
        print(f"""
hint: {details.hint}
title: {details.title}
description:
    {description}
related:
    {related}
        """.strip())
        
        sub_name = details.hint
        
    else:
        sub_name = input('pick a name for the subscription: ')
        if not sub_name:
            sys.exit(0)
    
    try:
        return plugin.subscribe(sub_name, options=options)
        
    except IntegrityError:
        session.rollback()
        
        is_name_conflict = session.query(
                session.query(Subscription) \
                        .filter(Subscription == sub_name) \
                        .exists()
                ).scalar()
        
        print()
        if is_name_conflict:
            fail('a subscription with the same name exists')
            
        else:
            fail(f'this subscription already exists')

if __name__ == '__main__':
    argc = len(sys.argv)
    if argc == 1:
        usage()
        sys.exit(0)
    
    config = hoordu.load_config()
    hrd = hoordu.hoordu(config)
    
    args = parse_args(hrd)
    
    if args.command is None:
        if len(args.urls) == 1 and isinstance(args.urls[0][1], hoordu.Dynamic):
            plugin_id, options = args.urls[0]
            with hrd.session() as session:
                process_sub(session, plugin_id, options)
            
        else:
            with hrd.session() as session:
                for plugin_id, post_id in args.urls:
                    plugin = session.plugin(plugin_id)
                    plugin.download(post_id)
                    session.commit()
        
        
    elif args.command == 'setup':
        setup_plugin(hrd, args.plugin_id)
        
        
    elif args.command == 'list':
        with hrd.session() as session:
            subs = session.query(Subscription) \
                    .join(Source) \
                    .filter(Source.name == args.source)
            for sub in subs:
                if sub.enabled ^ args.disabled:
                    print(f'\'{sub.name}\': {(sub.options)}')
        
        
    elif args.command in ('enable', 'disable'):
        with hrd.session() as session:
            if args.source is not None:
                sub = session.query(Subscription) \
                        .join(Source) \
                        .filter(
                            Source.name == args.source,
                            Subscription.name == args.subscription
                        ).one()
                
            else:
                sub = session.query(Subscription) \
                        .filter(
                            Subscription.name == args.subscription
                        ).one()
            
            sub.enabled = (args.command == 'enable')
            session.add(sub)
        
        
    elif args.command == 'update' and args.subscription is None:
        with hrd.session() as session:
            if args.plugin_id is not None:
                # filter by plugin
                subs = session.query(Subscription) \
                        .join(Plugin) \
                        .filter(Plugin.name == args.plugin_id)
                
            else:
                # filter by source
                subs = session.query(Subscription) \
                        .join(Source) \
                        .filter(Source.name == args.source)
            
            for sub in subs:
                if sub.enabled:
                    print(f'getting all new posts for subscription \'{sub.name}\'')
                    plugin = session.plugin(sub.plugin.name)
                    it = plugin.create_iterator(sub, direction=FetchDirection.newer, num_posts=None)
                    safe_fetch(session, it)
                    session.commit()
        
    elif args.command in ('update', 'fetch', 'rfetch'):
        with hrd.session() as session:
            if args.plugin_id is not None:
                # filter by plugin
                sub = session.query(Subscription) \
                        .join(Plugin) \
                        .filter(
                            Plugin.name == args.plugin_id,
                            Subscription.name == args.subscription
                        ) \
                        .one_or_none()
                
            else:
                # filter by source
                sub = session.query(Subscription) \
                        .join(Source) \
                        .filter(
                            Source.name == args.source,
                            Subscription.name == args.subscription
                        ) \
                        .one_or_none()
            
            if sub is None:
                fail(f'subscription \'{args.subscription}\' doesn\'t exist')
            
            direction = FetchDirection.older if args.command == 'fetch' else FetchDirection.newer
            
            it = plugin.create_iterator(sub, direction=direction, num_posts=args.num_posts)
            safe_fetch(session, it)
            
            if sub.plugin_id != plugin.plugin.id:
                # set the preferred plugin to last used plugin
                sub.plugin_id = plugin.plugin.id
                session.add(sub)
                session.commit()
        
    elif args.command == 'related':
        with hrd.session() as session:
            plugin_id, post_id = args.urls[0]
            plugin = session.plugin(plugin_id)
            post = plugin.download(post_id)
            session.commit()
            
            for plugin_id, post_id in args.urls[1:]:
                plugin = session.plugin(plugin_id)
                related_post = plugin.download(post_id)
                session.add(Related(related_to=post, remote=related_post))
                session.commit()


