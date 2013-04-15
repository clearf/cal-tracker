#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Main site"""

# Typical imports
import sys
import argparse
from functools import wraps
from datetime import datetime

# Web tools
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, abort
import urllib
import json

# Our database definitions
from db.common import app, db, FlyingEvent, event_sort_order

def renderme(page, file_id=None): 
    if file_id:
        page_content = BlogPost.query.filter_by(file_id=file_id).first_or_404()
    else:
        page_content = None
    return render_template(page + '.html', page='/'+page+'/', page_content=page_content) 

##### Routes
@app.route('/')
def index():
    # Note: to reset the form in JS, do: $('#newrequest').get(0).reset();
    # XXX Consider: Templates are very general, and content is queried from google docs?
    # Or, some templates are specific with flashy content, and only things like blogs come from google
    return redirect(url_for('overview'))

@app.route('/overview/')
def overview():
    return renderme('overview')

@app.route('/services/')
def services():
    return renderme('services')

@app.route('/team/')
def team():
    file_id='1XvQhNs6WcLrogwNDixPeVoW0p4SX8hKgHYvw0eMiJeo'
    return renderme('team', file_id)

@app.route('/whitepapers/')
def whitepapers():
    return renderme('whitepapers')

@app.route('/contact/')
def contact():
    return renderme('contact')

@app.route('/commentary/')
def commentary():
    if app.debug: 
        queried_posts = BlogPost.query.order_by(*post_sort_order).all()
    else:
        queried_posts = BlogPost.query.filter_by(status='published').order_by(*post_sort_order).all()
    headline_post = queried_posts[0]
    # XXX include a pager here
    other_posts = queried_posts[1:4]
    return render_template('commentary.html', page='/commentary/', headline_post=headline_post, other_posts=other_posts) 

@app.route('/commentary/posts/<string:title_url>')
def post_page(title_url):
    unique_title=urllib.unquote(title_url)
    post = BlogPost.query.filter_by(unique_title=unique_title).first_or_404()
    prev_post, next_post=post.get_adjacent_posts()
    return render_template('post.html', page='/commentary/', post=post, prev_post=prev_post, next_post=next_post)

@app.route('/pieces/posts')
def get_posts():
    if app.debug: 
        queried_posts = BlogPost.query.order_by(*post_sort_order).all()
    else:
        queried_posts = BlogPost.query.filter_by(status='published').order_by(*post_sort_order).all()
    for post in queried_posts:
        processed_posts.append(post.preview())
    return Response(json.dumps(processed_posts), mimetype='application/json')

##### Main
def main(args=None, parser=None):
    def make_parser(parents=[]):
        """Make a command line parser appropriate for calling this module as a
        standalone script.
        """
        p = argparse.ArgumentParser(description=__doc__, parents=parents,
                                    add_help=True if not parents else False)
        p.add_argument('--debug', action='store_true')
        p.set_defaults()
        return p
    if args is None:
        args = sys.argv[1:]
    parser = parser or make_parser()
    opts = parser.parse_args(args)
    if opts.debug:
        app.debug = True
    app.run()
    return 0

app.secret_key = '>O8#P+RxSI&opa0HsDIk'

# What does this do?
if __name__ == '__main__':
    sys.exit(main())
