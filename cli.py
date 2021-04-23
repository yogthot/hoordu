#!/usr/bin/env python3

import sys
from pathlib import Path
import importlib.util
import traceback
from getpass import getpass

import hoordu
from hoordu.models import Source, Subscription
from hoordu.plugins import FetchDirection
from hoordu.forms import *

def usage():
    print('python {0} <plugin> <command> [command arguments]'.format(sys.argv[0]))
    print('')
    print('available commands:')
    print('    download <url>')
    print('        attempts to download the given url')
    print('')
    print('    sub <sub_name> <url>')
    print('        creates a subscription with the given name and feed')
    print('')
    print('    unsub <sub_name>')
    print('        deletes a subscription')
    print('')
    print('    list')
    print('        lists all subscriptions')
    print('')
    print('    update <sub_name>')
    print('        gets all new posts for a subscription')
    print('')
    print('    update-all')
    print('        gets all new posts for every subscription')
    print('')
    print('    fetch <sub_name> <n>')
    print('        gets <n> older posts for a subscription')
    print('')
    print('    rfetch <sub_name> <n>')
    print('        gets <n> newer posts from a subscription')

def fail(format, *args, **kwargs):
    print(format.format(*args, **kwargs))
    sys.exit(1)

def _cli_form(form):
    form.clear()
    
    print('== {} ==========='.format(form.label))
    for entry in form.entries:
        if isinstance(entry, Section):
            print('-- {} ----------'.format(entry.label))
            print()
            execute_form(entry)
            print('--------------' + '-' * len(entry.label))
        
        else:
            if entry.errors:
                for error in entry.errors:
                    print('error: {}'.format(error))
                
            if isinstance(entry, Label):
                print(entry.label)
                print()
                
            elif isinstance(entry, PasswordInput):
                value = getpass('{}: '.format(entry.label))
                if value: entry.value = value
                
            elif isinstance(entry, ChoiceInput):
                print('{}:'.format(entry.label))
                for k, v in entry.choices:
                    print('    {}: {}'.format(k, v))
                value = input('pick a choice: ')
                if value: entry.value = value
                
            elif isinstance(entry, Input):
                value = input('{}: '.format(entry.label))
                if value: entry.value = value
                
            else:
                print()

def cli_form(form):
    _cli_form(form)
    while not form.validate():
        _cli_form(form)

# this should be the general approach to initialization of a plugin
def init_plugin(hrd, name, form=None):
    cli_form(form)
    
    while True:
        # attempt to init
        success, plugin = hrd.load_plugin(name, parameters=form.value)
        
        if success:
            return plugin
        
        elif plugin is not None:
            # if not successful but something else was returned
            # then attempt to ask the user for input
            
            form = plugin
            cli_form(form)
        
        else:
            print('something went wrong with the plugin initialization')
            sys.exit(1)

def safe_fetch(plugin, it, direction, n):
    posts = {}
    while True:
        try:
            for remote_post in it.fetch(direction=direction, n=n):
                posts[remote_post.id] = remote_post
            
            return posts
        except KeyboardInterrupt:
            raise
        except:
            traceback.print_exc()
            if it.subscription is not None:
                subscription = it.subscription
                name = subscription.name
                print('subscription "{0}" ran into an error'.format(name))
                print('y = retry; d = rollback, ignore and disable subscription; n = just rollback and ignore'.format(name))
                v = input('do you want to retry? (Ynd) ').lower()
                if not v: v = 'y'
                if v == 'y':
                    # make sure we retry from a valid db state
                    plugin.core.flush()
                    if n is not None:
                        n -= len(posts)
                    continue
                    
                elif v == 'd':
                    plugin.core.rollback()
                    
                    subscription.enabled = False
                    plugin.core.add(subscription)
                    plugin.core.commit()
                    return
                    
                else:
                    raise

def process_url(hrd, url):
    plugins = hrd.load_plugins()
    
    for plugin in plugins.values():
        options = plugin.parse_url(url)
        
        if isinstance(options, str):
            plugin.download(options)
            plugin.core.commit()
        
        elif isinstance(options, hoordu.Dynamic):
            details = plugin.get_search_details(options)
            
            if details is not None:
                print("""
hint: {}
title: {}
description:
    {}
related:
    {}
                """.format(details.hint,
                            details.title,
                            details.description.replace('\n', '\n    '),
                            '\n    '.join(details.related_urls)).strip())
                
                v = input('subscribe to this url? (Yn) ').lower()
                if not v: v = 'y'
                if v == 'y':
                    plugin.create_subscription(details.hint, options=options)
                    plugin.core.commit()
                
            else:
                sub_name = input('pick a name for the subscription: ')
                if sub_name:
                    plugin.create_subscription(sub_name, options=options)
                    plugin.core.commit()
            
        else:
            continue
        
        return

if __name__ == '__main__':
    if len(sys.argv) == 1:
        usage()
        sys.exit(1)
    
    config = hoordu.load_config()
    hrd = hoordu.hoordu(config)
    
    if len(sys.argv) == 2:
        process_url(hrd, sys.argv[1])
        
    else:
        plugin_name = sys.argv[1]
        command = sys.argv[2]
        args = sys.argv[3:]
        
        status, plugin = hrd.load_plugin(plugin_name)
        if not status:
            form = plugin
            plugin = init_plugin(hrd, plugin_name, form)
        
        core = plugin.core
        
        try:
            if command == 'download':
                url = args[0]
                
                id = plugin.parse_url(url)
                if isinstance(id, str):
                    remote_post = plugin.download(id, preview=False)
                    core.commit()
                    
                    print('related urls:')
                    for related in remote_post.related:
                        print('    {}'.format(related.url))
                else:
                    fail('can\'t download the given url: {0}', url)
                
            elif command == 'sub':
                sub_name = args[0]
                url = args[1]
                
                sub = core.session.query(Subscription).filter(Subscription.source_id == plugin.source.id, Subscription.name == sub_name).one_or_none()
                if sub is None:
                    print('creating subscription {0} for {1}'.format(repr(sub_name), url))
                    options = plugin.parse_url(url)
                    if isinstance(options, hoordu.Dynamic):
                        sub = plugin.create_subscription(sub_name, options=options)
                        core.commit()
                    else:
                        fail('invalid url')
                    
                else:
                    fail('subscription named \'{0}\' already exists', sub_name)
                
            elif command == 'list':
                subs = core.session.query(Subscription).filter(Subscription.source_id == plugin.source.id)
                for sub in subs:
                    print('\'{0}\': {1}'.format(sub.name, sub.options))
                
            elif command == 'update':
                sub_name = args[0]
                
                sub = core.session.query(Subscription).filter(Subscription.source_id == plugin.source.id, Subscription.name == sub_name).one_or_none()
                if sub is not None:
                    print('getting all new posts for subscription \'{0}\''.format(sub_name))
                    it = plugin.get_iterator(sub)
                    it.init()
                    safe_fetch(plugin, it, FetchDirection.newer, None)
                    core.commit()
                    
                else:
                    fail('subscription named \'{0}\' doesn\'t exist', sub_name)
                
            elif command == 'update-all':
                subs = core.session.query(Subscription).filter(Subscription.source_id == plugin.source.id)
                for sub in subs:
                    if sub.enabled:
                        try:
                            print('getting all new posts for subscription \'{0}\''.format(sub.name))
                            it = plugin.get_iterator(sub)
                            it.init()
                            safe_fetch(plugin, it, FetchDirection.newer, None)
                            core.commit()
                        except KeyboardInterrupt:
                            raise
                        except:
                            traceback.print_exc()
                            core.rollback()
                
            elif command == 'fetch':
                sub_name = args[0]
                num_posts = int(args[1])
                
                sub = core.session.query(Subscription).filter(Subscription.source_id == plugin.source.id, Subscription.name == sub_name).one_or_none()
                if sub is not None:
                    print('fetching {0} older posts for subscription \'{1}\''.format(num_posts, sub_name))
                    it = plugin.get_iterator(sub)
                    it.init()
                    safe_fetch(plugin, it, FetchDirection.older, num_posts)
                    core.commit()
                    
                else:
                    fail('subscription named \'{0}\' doesn\'t exist', sub_name)
                
            elif command == 'rfetch':
                sub_name = args[0]
                num_posts = int(args[1])
                
                sub = core.session.query(Subscription).filter(Subscription.source_id == plugin.source.id, Subscription.name == sub_name).one_or_none()
                if sub is not None:
                    print('fetching {0} newer posts for subscription \'{1}\''.format(num_posts, sub_name))
                    it = plugin.get_iterator(sub)
                    it.init()
                    safe_fetch(plugin, it, FetchDirection.newer, num_posts)
                    core.commit()
                    
                else:
                    fail('subscription named \'{0}\' doesn\'t exist', sub_name)
            
            elif command == 'unsub':
                sub_name = args[0]
                
                core.session.query(Subscription).filter(Subscription.source_id == plugin.source.id, Subscription.name == sub_name).delete()
                core.commit()
            
        except SystemExit:
            pass
            
        except:
            traceback.print_exc()
            # rollback whatever was being done at the time
            core.rollback()
            sys.exit(1)


