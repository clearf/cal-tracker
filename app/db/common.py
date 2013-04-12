# -*- coding: utf-8 -*-

# Flask. We just need the basic stuff in this common moduel
from flask import Flask

# flask SQLAlchemy
from flask.ext.sqlalchemy import SQLAlchemy

# Sort
from sqlalchemy import desc,asc,and_
# Deferred columns 
from sqlalchemy.orm import deferred

# Let's us use a class property as a DB query lookup
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql.expression import func

from bs4 import BeautifulSoup
import re
from datetime import datetime, date
import os
import urllib

def get_full_db_path(file):
  return os.path.join(os.path.dirname(os.path.abspath(__file__)), file)

db_path = 'sqlite:///' + get_full_db_path('caltracker.sqlite')
app = Flask('app')
app.config['SQLALCHEMY_DATABASE_URI'] = db_path
db = SQLAlchemy(app)

custom_tag = '.google-content'

class BlogPost(db.Model):
    # File metadata
    file_id = db.Column(db.Text, primary_key=True)
    modified_date = db.Column(db.DateTime)

    # Post metadata
    title = db.Column(db.UnicodeText)
    post_date = db.Column(db.Date)
    author = db.Column(db.UnicodeText)
    tags = db.Column(db.UnicodeText)
    status = db.Column(db.UnicodeText)

    # Content
    # XXX consider making all of these "Deferred"
    stylesheets = db.Column(db.UnicodeText)
    body = db.Column(db.UnicodeText)
    body_string = db.Column(db.UnicodeText)
    img_src = db.Column(db.UnicodeText)
    img_tag = db.Column(db.UnicodeText)

    def __init__(self, file_id, modified_date, html_doc):
        self.file_id = file_id
        self.update_post(modified_date, html_doc)

    def update_post(self, modified_date, html_doc):
        self.modified_date=datetime.strptime(modified_date, '%Y-%m-%dT%H:%M:%S.%fZ')
        self.soup = BeautifulSoup(html_doc)
        self.extract_finished=False
        self.process_body_and_extract_data()

    def __lt__(self, new_date):
        return self.modified_date < datetime.strptime(new_date, '%Y-%m-%dT%H:%M:%S.%fZ')
    def __gt__(self, new_date):
        return self.modified_date > datetime.strptime(new_date, '%Y-%m-%dT%H:%M:%S.%fZ')
    def __lte__(self, new_date):
        return self.modified_date <= datetime.strptime(new_date, '%Y-%m-%dT%H:%M:%S.%fZ')
    def __gte__(self, new_date):
        return self.modified_date >= datetime.strptime(new_date, '%Y-%m-%dT%H:%M:%S.%fZ')
    #def __eq__(self, new_date):
    #    return self.modified_date == datetime.strptime(new_date, '%Y-%m-%dT%H:%M:%S.%fZ')
    #def __neq__(self, new_date):
    #    return self.modified_date != datetime.strptime(new_date, '%Y-%m-%dT%H:%M:%S.%fZ')

    def process_body_and_extract_data(self):
      def append_attrib(tag, attrib_value, attrib='class'):
        if attrib in tag:
          if isinstance(tag[attrib],list): 
            values = tag[attrib]
            values.append(attrib_value)
            tag[attrib] = values
          else:
            tag[attrib] = [tag[attrib], attrib_value]
        else:
          tag[attrib] = attrib_value
      def remove_google_comments():
          # Remove "comment" links in the text
          for a in self.soup.find_all(href=re.compile('^#cmnt\d+')):
            a.extract()
          # Find the links in the comment divs 
          # and remove the divs
          for a in self.soup.find_all(href=re.compile('^#cmnt_ref\d+')):
            for parent in a.parents:
              if parent.name=='div':
                parent.extract()
                break
          # Add 'targets' to other links to make them external
          for a in self.soup.find_all(href=re.compile('^[^#]')):
            a['target'] = '_blank'

          # Add 'targets' to other links to make them external
          for a in self.soup.find_all(href=re.compile('^#ftnt\d+')):
            a['style'] = 'font-size: 14px'

          # Don't like google's imposed paragraph formatting. See if this gets us in trouble
          #for p in self.soup.find_all('p'):
            #del p['class']
      def parse_metadata():
          def extract_raw_metadata():
              ENDTITLE='\|ENDTITLE\|\s*$'
              if self.extract_finished:
                  print "Already extracted!"
                  return
              # Any text to the left of the ENDTITLE is our title metadata
              metadatas=re.split(ENDTITLE, self.soup.body.p.get_text())
              # There must exist exactly ONE ENDTITLE in the first line.
              if len(metadatas)!=2:
                  # XXX introduce some reasonable exception handling
                  print "Error" 
                  return
              self.raw_metadata=metadatas[0]
              # Then remove the first P, which we know is the ENDTITLE
              self.soup.body.p.extract()
              self.extract_finished=True
          if not self.extract_finished:
              extract_raw_metadata()
          metadata = re.split('\|', self.raw_metadata)
          # XXX better error handling here
          if len(metadata) != 5:
              print 'Error: Metadata not completely specified ' + repr(metadata)
              return
          title, post_date, author, tags, status = metadata
          self.title=title
          self.post_date=datetime.strptime(post_date, '%Y-%m-%d')
          self.author=author
          self.tags=tags
          self.status=status
      def extract_stylesheets():
        self.stylesheets =''
        for style_tag in self.soup.find_all('style'):
          self.stylesheets += custom_tag + ' ' + re.sub(r'(\})(.+?\{)', '\g<1> %s \g<2>' % custom_tag, style_tag.string)
      def extract_first_image():
        if self.soup.img:
          self.img_src = self.soup.img['src']
          self.img_tag = unicode(self.soup.img)
          self.soup.img.extract() # and, the image is gone
      def make_links_conform():
        for a in self.soup.find_all('a'):
          a['class']=''
      def transform_body():
          # Body is hard to deal with, so we make tfor chis a div with a
          # blogpost class
          self.soup.body.name='div'
          self.soup.div['class'] = re.sub(r'^\.', '', custom_tag) # Strip leading '.'
          self.body=unicode(self.soup.div)
          self.body_string=self.soup.div.get_text()
      remove_google_comments()
      parse_metadata()
      extract_stylesheets()
      extract_first_image()
      make_links_conform()
      transform_body()

    def body_excerpt(self, words=40):
        result=re.match(r"(\s*.+?\w+\s){%s,}?(.*)" % words, self.body_string)
        if result:
            idx=result.end(1)
            return self.body_string[:idx] 
        else:
            return self.body_string

    # hybrid property lets us make db-queries based off of this.
    @hybrid_property 
    def unique_title(self):
      # XXX not critical, but make a unit test later that ensures
      # no duplicate post title+file_ids.
      # We include 4 chars of the file_id to approximate uniquity. 
      return self.title + self.file_id[:4]
    @unique_title.expression
    def unique_title(cls):
      # BREAK this will break when we switch to another db backend
      # substr -> substring
      return cls.title + func.substr(cls.file_id,1,4)

    def title_url(self):
       return urllib.quote(self.unique_title)

    def get_adjacent_post(self, prev=True):
      def compare(a,b):
        if prev:
          return a < b
        else:
          return a > b
      if prev: 
        sort_order = desc
      else:
        sort_order = asc
      return BlogPost.query.filter(and_(compare(BlogPost.post_date, self.post_date),
                                        BlogPost.status=='published')).order_by(sort_order(BlogPost.post_date)).first()

    def get_adjacent_posts(self):
      return (self.get_adjacent_post(), self.get_adjacent_post(prev=False))

    def __str__(self): 
        return "Title: %s by %s Post Date: %s, Modified %s\n %s\n" % (self.title, self.author, self.post_date.strftime('%Y-%m-%d'),
                                             self.modified_date, self.body_excerpt())

    # XXX TODO: Make this print out something useful again
    def __repr__(self):
        return "file_id: %r title: %r author: %r Post Date: %r, Modified %r\n %r\n" % (self.file_id, self.title, self.author, self.post_date,
                                             self.modified_date, self.body_excerpt())

    def preview(self):
        return {'file_id': self.file_id, 'title': self.title,
                'post_date': self.post_date.strftime('%Y-%m-%d'), 'author': self.author, 'excerpt': self.body_excerpt(),
                'title_url': self.title_url(), 'img_src': self.img_src}

post_sort_order = [desc(BlogPost.post_date), BlogPost.modified_date]

