#!/usr/bin/env python

# Web and google api
import httplib2
import os
import sys
import argparse
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from apiclient import errors
from apiclient.discovery import build
import datetime
from pytz import timezone

from ..db.common import FlyingEvent, db
from sqlalchemy import desc,asc,and_


# Utilities
import json
import re
import random
import logging
import base64
import smtplib
logging.basicConfig()


# For parsing google drive
from bs4 import BeautifulSoup

def get_full_path(file):
  return os.path.join(os.path.dirname(__file__), file)

def email_to_name(email):
  if email=='rjt.vmi@gmail.com':
    return 'Rob'
  elif email=='jordanzaretsky@gmail.com':
    return 'Jordan'
  elif email=='mark.brager@gmail.com':
    return 'Mark'
  elif email=='chris.clearfield@gmail.com':
    return 'Chris'
  else:
    return email

def airplane_salutation():
  names=['The Mooney', 'N2201', 'The Speed Queen', 'Da Mooney', 'Your Airplane']
  return random.choice(names)

class SpreadsheetInterface:
  def __init__(self, http, send_mail, worksheet_url='0AvS2F7wRovC4dEpmMEFGYnJVVWZpV1RTUzZLYk5UTnc'):
    self.drive_http = http
    # Try to download a specific google drive row
    google_base_url='https://spreadsheets.google.com/feeds/list/'
    self.data_url = google_base_url + worksheet_url + '/od4/private/full'
    self.log_url =  google_base_url + worksheet_url + '/od5/private/full'
    self.send_mail = send_mail
    self.get_data_contents()

  def get_data_contents(self):
    resp, content = self.drive_http.request(self.data_url)
    if resp.status == 200:
      self.data_soup=BeautifulSoup(content)
    else:
      raise Exception("Unable to get resource %r" % resp)

  # Returns false if they differ
  def row_equal_to_event(self, event, entry_tag) :
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
    tach_diff = event.tach_end - event.tach_start
    return """<entry xmlns="http://www.w3.org/2005/Atom" xmlns:gsx="http://schemas.google.com/spreadsheets/2006/extended">
         <gsx:date>%s</gsx:date>
         <gsx:pilotusername>%s</gsx:pilotusername>
         <gsx:tachstart>%s</gsx:tachstart>
         <gsx:tachend>%s</gsx:tachend>
         <gsx:tachtime>%s</gsx:tachtime>
         <gsx:eventid>%s</gsx:eventid>
    </entry>""" % (event.end_date.strftime('%Y-%m-%d'), event.creator_email,
                      event.tach_start, event.tach_end, tach_diff, event.event_id)

  def update_entry(self, event, edit_url):
    headers = {"Content-type": "application/atom+xml"}
    try:
      new_entry=self.entry_tag_from_event(event)
    except TypeError as e:
      raise Exception("%r: Unable to upload event %r, probably tach time" % (e, event))
      
    resp, content = self.drive_http.request(edit_url, "PUT", new_entry, headers)
    # Success
    if resp.status == 200:
      return content
    else:
      raise Exception("Unable to upload event %r, response: %r" % (event, resp))

  def upload_new_entry(self, event):
    headers = {"Content-type": "application/atom+xml"}
    try:
      new_entry=self.entry_tag_from_event(event)
    except TypeError as e:
      raise Exception("%r: Unable to upload event %r, probably tach time" % (e, event))
    resp, content = self.drive_http.request(self.data_url, "POST", new_entry, headers)
    # Created
    if resp.status == 201:
      return content
    else:
      raise Exception("Unable to upload event %r, response: %r" % (event, resp))

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
    
      
  # Events in the past
  # Check these events for tach 
  def check_past_events_for_tach(self):
    events=FlyingEvent.query.filter(and_(FlyingEvent.end_date >  datetime.datetime(2013,04,01).date(), # This is from when we have good data
                                         FlyingEvent.end_date <  datetime.datetime.today().date(),
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
  def __init__(self, argument_opts, credentials_path=get_full_path('credentials.secret'),
               calendar_id='r86s1non6cr5dsmmjk38580ol4@group.calendar.google.com', username='2201aviation@gmail.com'):
    # Generate or retrieve our credentials from storage
    self.setup_credentials(credentials_path)
    self.calendar_id = calendar_id
    self.opts = argument_opts
    self.username=username

    # Initalize our services
    self.drive_service, self.drive_http=self.build_service()
    self.cal_service, self.cal_http=self.build_service(service_name='calendar')

  def build_service(self, service_name='drive'):
    """Build a service object.
    Args:
      credentials: OAuth 2.0 credentials.
    Returns:
      Drive service object.
    """
    if service_name=='drive':
      version='v2'
    elif service_name=='calendar':
      version='v3'
    else:
      return "Service not supported"
    http = httplib2.Http()
    http = self.credentials.authorize(http)
    return build(service_name, version, http=http), http

  def setup_credentials(self, credentials_path): 
    if os.path.exists(credentials_path):
      storage=Storage(get_full_path('credentials.secret'))
      self.credentials=storage.get()
    else:  
      flow = flow_from_clientsecrets(get_full_path('client_secrets.json'),
                                   scope='https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/drive https://spreadsheets.google.com/feeds https://docs.google.com/feeds https://mail.google.com/',
                                   redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                                     )
      auth_uri=flow.step1_get_authorize_url()
      # We've used the "installed" auth feature to get our code already. 
      json_data = open(get_full_path('code.json'))
      data = json.load(json_data)
      code = data['code']
      credentials = flow.step2_exchange(code)
      storage = Storage(credentials_path)
      storage.put(credentials)
      self.credentials=credentials

  def send_mail(self, msg, subject='2201 Aviation', recipient='chris.clearfield@gmail.com'):
    def generate_oauth2_string(base64_encode=True):
      """Generates an IMAP OAuth2 authentication string.
      See https://developers.google.com/google-apps/gmail/oauth2_overview
      Args:
        access_token: An OAuth2 access token.
        base64_encode: Whether to base64-encode the output.
      Returns:
        The SASL argument for the OAuth2 mechanism.
      """
      auth_string = 'user=%s\1auth=Bearer %s\1\1' % (self.username, self.credentials.access_token)
      if base64_encode:
        auth_string = base64.b64encode(auth_string)
      return auth_string
    msg = 'From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n' % (self.username, recipient, subject) + msg
    if not self.opts.nomail:
      smtp_conn = smtplib.SMTP('smtp.gmail.com', 587)
      smtp_conn.ehlo()
      smtp_conn.starttls()
      smtp_conn.ehlo()
      smtp_conn.docmd('AUTH', 'XOAUTH2 ' + generate_oauth2_string())
      logging.debug(msg)
      smtp_conn.sendmail(self.username, recipient, msg)
      smtp_conn.quit()
    else:
      print msg
    

  def update_db_events(self):
    def query_events():
      # Pull the calendar timezone 
      cal_tz = self.cal_service.calendars().get(calendarId=self.calendar_id).execute()['timeZone']
      time_format = '%Y-%m-%dT%H:%M:%S'
      # A static time for which our calendar entries are well formatted.
      timeMin=datetime.datetime(2013,04,01,0,0,0, tzinfo=timezone(cal_tz)).strftime(time_format+'%z')
      events = self.cal_service.events().list(calendarId=self.calendar_id, orderBy='startTime', singleEvents=True,
                                              timeMin=timeMin, showDeleted=True).execute()
      if events['items']:
        return events['items'] 
      else:
        None
    for cal_event in query_events():
      updated_datetime = cal_event['updated']
      db_event=FlyingEvent.query.filter_by(event_id=cal_event['id']).first()
      # New post, add to DB
      if db_event == None:
         logging.debug("Adding new calendar event %r" % cal_event)
         db_event=FlyingEvent(cal_event['id'], updated_datetime, cal_event)
         db.session.add(db_event)
      else:
        if db_event<updated_datetime:
          logging.debug("Updating db from calendar %r" % cal_event)
          db_event.update_event(updated_datetime, cal_event)
        else:
          if self.opts.refresh:
            if cal_event['status']!='cancelled':
              logging.debug("Forcing db update from calendar %r" % cal_event)
            db_event.update_event(updated_datetime, cal_event)
      db.session.commit()

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
  gg.update_db_events()

  ss=SpreadsheetInterface(gg.drive_http, gg.send_mail)
  ss.process_followup()
  ss.check_past_events_for_tach()

  ## XXX TODO:
  ## Deploy... 
  ## Program in "points" system for future events
  ## Pie in sky: Make a webpage where people can go to add missing hours, view points in use, etc
  
if __name__ == '__main__':
    sys.exit(main())
