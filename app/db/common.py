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

import re
from datetime import datetime, date
import os
import urllib

# Utility functions
def get_full_db_path(file):
  return os.path.join(os.path.dirname(os.path.abspath(__file__)), file)

def convert_google_date(raw_date, frmt):
  if frmt=='datetime':
    frmt = '%Y-%m-%dT%H:%M:%S'
  elif frmt=='google_ts':
    frmt = '%Y-%m-%dT%H:%M:%S.%fZ'
  else:
    frmt = '%Y-%m-%d'
  # XXX we totally discard TZ info. It's hard to deal with, and we don't really nead it here. 
  def strip_tz_info(raw_date):
    return re.sub('(.+)([+-]\d{2}:\d{2})$','\g<1>', raw_date) 
  try: 
    conv_date = datetime.strptime(strip_tz_info(raw_date), frmt)
    if conv_date==None:
      raise ValueError('Error converting %s' % (raw_date))
    else:
      return conv_date
  except Exception as e:
    raise ValueError('%r, converting %s' % (e, raw_date))
    

db_path = 'sqlite:///' + get_full_db_path('caltracker.sqlite')
app = Flask('app')
app.config['SQLALCHEMY_DATABASE_URI'] = db_path
db = SQLAlchemy(app)

class FlyingEvent(db.Model):
    # Event Data
    event_id = db.Column(db.Text, primary_key=True)
    updated_datetime = db.Column(db.DateTime)
    start_date = db.Column(db.DateTime)
    end_date = db.Column(db.DateTime)
    status = db.Column(db.Text)
    creator_email = db.Column(db.Text)
    summary = db.Column(db.Text)
    description = db.Column(db.Text)

    # Flying-specific entries
    flying = db.Column(db.Boolean)
    tach_start = db.Column(db.Float)
    tach_end = db.Column(db.Float)

    def __init__(self, event_id, updated_datetime, event):
        self.event_id = event_id
        self.update_event(updated_datetime, event)

    def update_event(self, updated_datetime, event):
        self.updated_datetime=convert_google_date(updated_datetime, 'google_ts')
        self.process_event_and_extract_data(event)

    def __lt__(self, new_date):
        return self.updated_datetime < convert_google_date(new_date, 'google_ts')
    def __gt__(self, new_date):
        return self.updated_datetime > convert_google_date(new_date, 'google_ts')
    def __lte__(self, new_date):
        return self.updated_datetime <= convert_google_date(new_date, 'google_ts')
    def __gte__(self, new_date):
        return self.updated_datetime >= convert_google_date(new_date, 'google_ts')
      
    def process_event_and_extract_data(self, event):
      def set_flying():
        try:
          if event['description']=='NOFLY':
            self.flying=False
          else:
            self.flying=True
        except:
          self.flying=True
      def get_event_date(date_structure):
        try: 
          if 'dateTime' in date_structure:
            return convert_google_date(date_structure['dateTime'], 'datetime')
          else:
            return convert_google_date(date_structure['date'], 'date')
        except:
          raise ValueError('Bad Date Structure %r' % date_structure)
      def extract_hours():
        def get_digits(line):
          try: 
            return float(line)
          except ValueError:
            return None
        try: 
          if self.flying and self.end_date.date() < date.today():
            lines = self.description.split('\n')
            self.tach_start = get_digits(lines[0])
            self.tach_end = get_digits(lines[1])
        except Exception as e:
          raise Exception('%r, Could not parse tach %r' % (e, self))
      def gather_data():
        set_flying()
        self.creator_email = event['creator']['email']
        self.start_date = get_event_date(event['start'])
        self.end_date = get_event_date(event['end'])
        self.status = event['status']
        try:
          self.summary = event['summary']
        except:
          print 'No summary: %r'
        try:
          self.description = event['description']
        except:
          self.description = ""
        print repr(self)
        extract_hours()
      gather_data()

    def get_adjacent_event(self, prev=True):
      def compare(a,b):
        if prev:
          return a < b
        else:
          return a > b
      if prev: 
        sort_order = desc
      else:
        sort_order = asc
      return FlyingEvent.query.filter(and_(compare(FlyingEvent.end_date, self.end_date),
                                        FlyingEvent.flying==True)).order_by(sort_order(FlyingEvent.end_date)).first()

    def __str__(self): 
        return "%s \t %s \t %g \t %g \t %g \t %s" % (self.end_date.strftime('%Y-%m-%d'), self.creator_email,
                                                  self.tach_start, self.tach_end, self.tach_end - self.tach_start, self.event_id)

    def __repr__(self):
        return '{ "event_id": %r, "update_datetime": %r, "start_date": %r, "end_date": %r, "status": %r,\
        "creator_email": %r, "summary": %r, "description": %r, "flying": %r, "tach_start": %r, "tach_end": %r}' % (self.event_id, 
         self.updated_datetime,  
         self.start_date, 
         self.end_date,
         self.status,
         self.creator_email,
         self.summary,
         self.description,
         self.flying, 
         self.tach_start,
         self.tach_end)

event_sort_order = [desc(FlyingEvent.end_date), FlyingEvent.start_date]
