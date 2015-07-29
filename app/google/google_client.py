#!/usr/bin/env python

# Web and google api

import boto

import httplib2
from email.mime.text import MIMEText
import os
import sys
import argparse
from oauth2client.client import Credentials
from apiclient import errors
from apiclient.discovery import build
import datetime
from pytz import timezone
from urllib import urlencode

from ..db.common import FlyingEvent, db, email_to_name, airplane_salutation
from sqlalchemy import desc,asc,and_

# Utilities
import json
import re
import logging
import base64
import smtplib
logging.basicConfig()

# For parsing google drive
from bs4 import BeautifulSoup

def get_full_path(file):
  return os.path.join(os.path.dirname(__file__), file)


class SpreadsheetInterface:
  def __init__(self, http, send_mail, cal_tz, worksheet_url='0AvS2F7wRovC4dEpmMEFGYnJVVWZpV1RTUzZLYk5UTnc'):
    self.drive_http = http
    # Try to download a specific google drive row
    google_base_url='https://spreadsheets.google.com/feeds/list/'
    self.data_url = google_base_url + worksheet_url + '/od4/private/full'
    self.log_url =  google_base_url + worksheet_url + '/od5/private/full'
    self.send_mail = send_mail
    self.cal_tz = cal_tz
    self.get_data_contents()

  def get_data_contents(self):
    resp, content = self.drive_http.request(self.data_url)
    self.cookie = resp['set-cookie']
    if resp.status == 200:
      self.data_soup=BeautifulSoup(content)
    else:
      raise Exception("Unable to get resource %r" % resp)

  # Returns false if they differ
  def row_equal_to_event(self, event, entry_tag):
    def entry_to_dict():
      dict = {}
      for data in entry_tag.find_all(re.compile('^gsx:')):
        key = re.sub('gsx:', '', data.name)
        dict[key]=data.text
      return dict
    retval = True
    # Transform both objects to dict
    entry=entry_to_dict()
    event=eval(repr(event))
    for key in event:
      # Google spreadsheet removes _s
      keysub=re.sub('_','',key)
      if keysub in entry:
        if str(event[key]) != str(entry[keysub]): 
          failure = False
          try:
             if float(event[key]) == float(entry[keysub]):
                # Actually, we're OK, as they're floats and they match
                pass
             else:
                failure = True
          except:
            failure = True
          if failure:
           logging.warning('Key %s didn\'t match %s != %s, %r' % (key, str(event[key]), str(entry[keysub]), entry))
           return False
    return retval
    
  def check_for_updated_event(self, event):
    event_id = self.data_soup.find('gsx:eventid', text=event.event_id)
    if event_id: 
      if not self.row_equal_to_event(event, event_id.parent):
        content = event_id.parent
      else:
        content = None
      return True, content
    else:
      return False, None

  def entry_tag_from_event(self,event):
    try: 
      tach_diff = event.tach_end - event.tach_start
      return """<entry xmlns="http://www.w3.org/2005/Atom" xmlns:gsx="http://schemas.google.com/spreadsheets/2006/extended">
           <gsx:date>%s</gsx:date>
           <gsx:creatoremail>%s</gsx:creatoremail>
           <gsx:tachstart>%s</gsx:tachstart>
           <gsx:tachend>%s</gsx:tachend>
           <gsx:tachtime>%s</gsx:tachtime>
           <gsx:eventid>%s</gsx:eventid>
      </entry>""" % (event.end_date.strftime('%Y-%m-%d'), event.creator_email,
                        event.tach_start, event.tach_end, tach_diff, event.event_id)
    except TypeError:
      self.send_mail("Fellas,\n It looks like there's no ending tach in the calendar for \"%s\","
          "%s's event ending on %s\n" % (event.summary, event.creator_email, event.end_date.strftime('%Y-%m-%d')), 
          subject="Missing tach end", recipient='mooney-201@googlegroups.com')
      

  def update_entry(self, event, edit_url):
    headers = {"Content-type": "application/atom+xml; charset=UTF-8"}
    new_entry=self.entry_tag_from_event(event)
    if new_entry: 
      resp, content = self.drive_http.request(edit_url, "PUT", new_entry, headers)
      # Success
      if resp.status == 200:
        return content
      else:
        raise Exception("Unable to upload event %r, response: %r" % (event, resp))

  def upload_new_entry(self, event):
    headers = {"Content-Type": "application/atom+xml; charset=UTF-8"}
    headers['Cookie'] = self.cookie
    new_entry=self.entry_tag_from_event(event)
    if new_entry: 
      resp, content = self.drive_http.request(self.data_url, "POST", headers=headers, body=new_entry)
      # Created
      if resp.status == 201:
        return content
      else:
        raise Exception("Unable to upload event %r,\n response: %r,\n content: %r" % (event, resp, content))

  def process_followup(self):
    def followup_message(event):
      if event.start_date == event.end_date:
        return "\t%s on %s" % (event.summary, event.start_date, event.end_date)
      else:
        return "\t%s from %s to %s" % (event.summary, event.start_date, event.end_date)
    followup_events=FlyingEvent.query.filter(and_(FlyingEvent.send_followup==True, FlyingEvent.followup_sent==False)).all()
    followup_details={}

    # Process every event that has a followup "X"
    for followup_event in followup_events:
      followup_event.followup_sent=True
      db.update(followup_event)
      if followup_event.creator_email not in followup_details:
        followup_details[followup_event.creator_email] = followup_message(followup_event)
      else:
        followup_details[followup_event.creator_email] += '\n' + followup_message(followup_event)
    db.session.commit()
    
    # Send out email for the followup we have gathered
    for email, flights in followup_details.iteritems():
      message = "%s, you indicated that you wanted to followup on some flights:\n%s\n" % (email_to_name(email), flights)
      message += "\n\nClick here to fill out the followup form:\n" 
      message += "https://docs.google.com/forms/d/1NlnetOPmJCm652Vq_hMii7wurDaJT8j1qVUr3LYspGo/viewform\n"
      message += "Thanks,\n%s" % airplane_salutation()
      self.send_mail(message, subject='Followup on flight', recipient=email)
    
  def calculate_users_points(self):
    def calculate_event_points(event):
      def count_weekends_infringed(event):
        weekends=0
        one_day=datetime.timedelta(days=1)
        first_day_counting=max(event.start_date, datetime.datetime.today())
        #first_day_counting=event.start_date
        # If we start on a weekend, count that as one weekend
        # And start our counting on the subsequent Monday. 
        if first_day_counting.weekday()==6:
          weekends+=1
          first_day_counting+=one_day
        elif first_day_counting.weekday()==5:
          weekends+=1
          first_day_counting+=one_day*2
        last_day_counting=event.end_date
        # If we end on a Saturday or Sunday, count that as a weekend
        # and start our counting on the Friday prior
        if last_day_counting.weekday()==5:
          weekends+=1
          last_day_counting-=one_day 
        elif last_day_counting.weekday()==6:
          weekends+=1
          last_day_counting-=one_day*2
        flying_day = first_day_counting
        # Count the weekends within our booking
        counted_weekends=0
        while flying_day <= last_day_counting:
          if flying_day.weekday() >= 5:
            counted_weekends+=1 
          flying_day+=one_day
        assert counted_weekends % 2 == 0
        return weekends + counted_weekends / 2 
      # End count_weekends_infringed
      continuous_start_date=max(event.start_date, datetime.datetime.today())
      booking_length = event.end_date - continuous_start_date
      if booking_length <= datetime.timedelta(days=0):
        return 0
      elif booking_length > datetime.timedelta(days=14):
        points = 999 # No more than two weeks allowed
      elif booking_length > datetime.timedelta(days=7): # 7 to 14 days
        points = 3 
        if count_weekends_infringed(event) > 2:
          points += 1 
      elif booking_length >= datetime.timedelta(days=1) and booking_length <= datetime.timedelta(days=7):
        points = 2
        if count_weekends_infringed(event) > 1:
          points += 1 
      else:
        points = 1 # Basic bookings are equal to 1 point
      return points
    # End calculate_vent_points

    events=FlyingEvent.query.filter(and_(FlyingEvent.end_date >=  datetime.datetime.today().date(),
                                          FlyingEvent.flying==True)).order_by(asc(FlyingEvent.end_date)).all()
    bookings={}
    for event in events:
      points=calculate_event_points(event)
      summary_text =  event.creator_email,  event.summary, str(event.start_date), str(event.end_date),  \
         event.end_date - max(event.start_date, datetime.datetime.today()), points
      if event.creator_email not in bookings:
        bookings[event.creator_email] = {
          'points': [points],
          'summary': [summary_text]
          }
      else:
        bookings[event.creator_email]['points'].append(points)
        bookings[event.creator_email]['summary'].append(summary_text)
    message = '' 
    for email, booking in bookings.iteritems():
      total_points = sum(booking['points'])
      logging.info(booking['summary'])
      # print booking['summary']
      message+='%s\t%d\n' % (email_to_name(email), total_points)
      if total_points > 4:
        message+='\t\t ^^^^ Too many points!\n'
    self.send_mail(message, subject='Booking points')
      
  # Events in the past
  # Check these events for tach 
  def check_past_events_for_tach(self):
    events=FlyingEvent.query.filter(and_(FlyingEvent.end_date >  datetime.datetime(2013,04,01).date(), # This is from when we have good data
                                         FlyingEvent.end_date <  datetime.datetime.now(self.cal_tz) - datetime.timedelta(days=1), #Add a one day grace period
                                         FlyingEvent.flying==True)).order_by(asc(FlyingEvent.end_date)).all()
    for i, event in enumerate(events):
      if i == 0:
        continue
      try: 
        if event.tach_start != events[i-1].tach_end:
          if event.tach_start == None:
            greeting = email_to_name(event.creator_email) + ",\nIt looks like you may have forgot to enter some data\n"
          elif events[i-1].tach_end == None:
            greeting = email_to_name(events[i-1].creator_email) + ",\nIt looks like you may have forgot to enter some data\n"
          else:
            greeting = "Fellas,\nI'm a little confused. It seems like someone's flight may be missing? Or maybe just some numbers are off...\n\
Here's what I'm seeing:\n\n"
          message= greeting + "Tach mismatch \n*****************\n\
          %s's end tach on %s (%s): \t %s\n\
          %s's start tach on %s (%s): \t %s\n\
          \nYour friend,\n%s" % (events[i-1].creator_email, events[i-1].end_date, events[i-1].summary, events[i-1].tach_end,
                                                  event.creator_email, event.start_date, event.summary, event.tach_start, airplane_salutation())
          
          self.send_mail(message, subject='Tach Mismatch', recipient='mooney-201@googlegroups.com')
          break
        else:
          # event_tag is none unless the event has changed
          event_exists, event_tag = self.check_for_updated_event(event)
          if event_exists:
            # If the event has changed, we update...
            if event_tag:
              logging.debug("Updating row for event %r..." % event)
              self.update_entry(event, event_tag.find('link', rel='edit')['href'])
          else: # It's a new event
            logging.debug("Adding spreadsheet row %r" % event)
            self.upload_new_entry(event)
      except (IndexError, ValueError) as e:
        raise Exception('Can\'t compare tachs: %r, %r, %r' % (e, event, events[i-1]))

class GoogleInterface:
  def __init__(self, argument_opts,
      calendar_id='r86s1non6cr5dsmmjk38580ol4@group.calendar.google.com', username='2201aviation@gmail.com'):
    
    # Generate or retrieve our credentials from storage
    self.username=username
    self.opts = argument_opts
    self.opts.debug=True
    self.setup_credentials()
    self.calendar_id = calendar_id

    # Initalize our services
    self.drive_service, self.drive_http=self.build_service()
    self.cal_service, self.cal_http=self.build_service(service_name='calendar')
    self.gmail_service, self.gmail_http=self.build_service(service_name='gmail')

  def build_service(self, service_name='drive'):
    """Build a service object.
    Args:
      credentials: OAuth 2.0 credentials.
    Returns:
      Drive service object.
    """
    if service_name=='gmail':
      version='v1'
    elif service_name=='drive':
      version='v2'
    elif service_name=='calendar':
      version='v3'
    else:
      return "Service not supported"
    http = httplib2.Http()
    http = self.credentials.authorize(http)
    return build(service_name, version, http=http), http

  def setup_credentials(self): 
      scope='https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/drive https://spreadsheets.google.com/feeds https://docs.google.com/feeds https://www.googleapis.com/auth/gmail.compose'

# This is what we do to get the credentials in the first place. 
      # Note the access_type *offline*
      #flow=OAuth2WebServerFlow(client_id="116366442836.apps.googleusercontent.com", client_secret="DfS28bOzihgyqyKjsgS0Rum7", 
      #  scope=scope, redirect_uri="urn:ietf:wg:oauth:2.0:oob", access_type="offline")
      #flow.step1_get_authorize_url()
      #code=<from_that_webpage>
      #credentials = flow.step2_exchange(code=code)
      # After that, we save the credentials as a json to s3 and retrieve them from there going forward
      conn=boto.connect_s3()
      # if Validate=True, boto validates by listing the contents of the bucket. But our ec2 IAM role doesn't have 
      # list permissions, just read for its directory
      bucket=conn.get_bucket('hobby.lyceum.dyn.dhs.org', validate=False) 
      credentials_string=bucket.get_key("cal-tracker/credentials.json").get_contents_as_string()
      self.credentials=Credentials.new_from_json(credentials_string)

  def send_mail(self, msg, subject='2201 Aviation', recipient='chris.clearfield@gmail.com'):
    message = MIMEText(msg)
    message['To'] = recipient
    message['From'] = self.username
    message['Subject'] = subject
    print message
    safe_message = {'raw': base64.urlsafe_b64encode(message.as_string())}

    if not self.opts.nomail:
      try:
        message = self.gmail_service.users().messages().send(userId=self.username, body=safe_message).execute()
        print 'Message Id: %s' % message['id']
        #threads = self.gmail_service.users().threads().list(userId=self.username).execute()
        #if threads['threads']:
          #for thread in threads['threads']:
            #print 'Thread ID: %s' % (thread['id'])
      except errors.HttpError, error:
        print 'An error occurred: %s' % error
    else:
      print msg
    

  def update_db_events(self):
    def query_events():
      # Pull the calendar timezone
      self.cal_tz = timezone(self.cal_service.calendars().get(calendarId=self.calendar_id).execute()['timeZone'])
      time_format = '%Y-%m-%dT%H:%M:%S'
      # A static time for which our calendar entries are well formatted.
      timeMin=datetime.datetime(2013,04,01,0,0,0, tzinfo=self.cal_tz).strftime(time_format+'%z')
      event_list = []
      page_token = None
      while True:
          events = self.cal_service.events().list(calendarId=self.calendar_id, orderBy='startTime', singleEvents=True,
                                              timeMin=timeMin, showDeleted=True, pageToken=page_token).execute()
          if events['items']:
              event_list += events['items']
          page_token = events.get('nextPageToken')

          if not page_token:
              break
      return event_list
    updated=False
    for cal_event in query_events():
      updated_datetime = cal_event['updated']
      db_event=FlyingEvent.query.filter_by(event_id=cal_event['id']).first()
      # New post, add to DB
      if db_event == None:
         logging.debug("Adding new calendar event %r" % cal_event)
         db_event=FlyingEvent(cal_event['id'], updated_datetime, cal_event, self.send_mail)
         db.session.add(db_event)
         updated=True
      else:
        if db_event<updated_datetime:
          logging.debug("Updating db from calendar %r" % cal_event)
          db_event.update_event(updated_datetime, cal_event, self.send_mail)
          updated=True
        else:
          if self.opts.refresh:
            if cal_event['status']!='cancelled':
              logging.debug("Forcing db update from calendar %r" % cal_event)
            updated=True
            db_event.update_event(updated_datetime, cal_event, None)
    # After processing everthing, commit and return whether or not we've updated
    db.session.commit()
    return updated
##### Main
def main(args=None, parser=None):
  def make_parser(parents=[]):
      """Make a command line parser appropriate for calling this module as a
      standalone script.
      """
      p = argparse.ArgumentParser(description=__doc__, parents=parents,
                                  add_help=True if not parents else False)
      p.add_argument('--debug', action='store_true')
      p.add_argument('--refresh', action='store_true')
      p.add_argument('--nomail', action='store_true')
      p.set_defaults()
      return p
  if args is None:
      args = sys.argv[1:]
  parser = parser or make_parser()
  opts = parser.parse_args(args)
  if opts.debug:
    log=logging.getLogger()
    log.setLevel(logging.DEBUG)
  gg = GoogleInterface(opts)
  updated=gg.update_db_events()
  ss=SpreadsheetInterface(gg.drive_http, gg.send_mail, gg.cal_tz)
  # We want to do this each time,
  # to email reminders if there is a problem.
  ss.check_past_events_for_tach()
  ss.process_followup()

  # This should only be done if there's been an update
  if updated:
    ss.calculate_users_points()

  ## XXX TODO:
  ## Deploy... 
  ## Program in "points" system for future events
  ## Pie in sky: Make a webpage where people can go to add missing hours, view points in use, etc
  
if __name__ == '__main__':
    sys.exit(main())
