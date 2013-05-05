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
    return redirect(url_for('squawks'))

@app.route('/squawks/')
def squawks():
    return render_template('squawks.html')

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
    app.run(port=5001)
    return 0

app.secret_key = '>O8#P+RxSI&opa0HsDIk'

# What does this do?
if __name__ == '__main__':
    sys.exit(main())
