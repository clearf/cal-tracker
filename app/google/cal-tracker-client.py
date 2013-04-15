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
from apiclient import errors
from datetime import datetime, date
from pytz import timezone

from ..db.common import FlyingEvent, db
from sqlalchemy import desc,asc,and_


# Utilities
import json
import re
import logging
logging.basicConfig()


# For parsing google drive
from bs4 import BeautifulSoup

def get_full_path(file):
  return os.path.join(os.path.dirname(__file__), file)


class SpreadsheetInterface:
  def __init__(self, http, worksheet_url='0AvS2F7wRovC4dEpmMEFGYnJVVWZpV1RTUzZLYk5UTnc'):
    self.drive_http = http
    # Try to download a specific google drive row
    google_base_url='https://spreadsheets.google.com/feeds/list/'
    self.data_url = google_base_url + worksheet_url + '/od4/private/full'
    self.log_url =  google_base_url + worksheet_url + '/od5/private/full'

  def get_data_contents(self):
    resp, content = self.drive_http.request(self.data_url)
    if resp.status == 200:
      self.content_soup=BeautifulSoup(content)
      if self_soup.find('entry', 
        return True, soup
      else:
        return False, None
    else:
      raise Exception("Unable to get resource %r" % resp)

  def check_for_and_get_single_event(self, event):
    resp, content = self.drive_http.request(self.data_url + '?sq=eventid=' + event.event_id)
    if resp.status == 200:
      soup=BeautifulSoup(content)
      if soup.entry:
        return True, soup
      else:
        return False, None
    else:
      raise Exception("Unable to get resource %r" % resp)

  def get_events()

  def upload_new_event(event):
    headers = {"Content-type": "application/atom+xml"}
    new_event="""<entry xmlns="http://www.w3.org/2005/Atom" xmlns:gsx="http://schemas.google.com/spreadsheets/2006/extended">
         <gsx:date>%s</gsx:date>
         <gsx:pilotusername>%s</gsx:pilotusername>
         <gsx:tachstart>%s</gsx:tachstart>
         <gsx:tachend>%s</gsx:tachend>
         <gsx:tachtime>%s</gsx:tachtime>
         <gsx:eventid>%s</gsx:eventid>
    </entry>""" % (event.end_date.strftime('%Y-%m-%d'), event.creator_email,
                      event.tach_start, event.tach_end, event.tach_end - event.tach_start, event.event_id)
    resp, content = drive_http.request(data_url, "POST", new_event, headers)
    if resp.status == 201:
      print "OK"
      return content
    else:
      print "Unable to upload event"
      return None
      
  # Events in the past
  def check_past_events():
    events=FlyingEvent.query.filter(and_(FlyingEvent.end_date >  datetime(2013,04,01).date(), # This is from when we have good data
                                         FlyingEvent.end_date <  datetime.today().date(),
                                         FlyingEvent.flying==True, )).order_by(asc(FlyingEvent.end_date)).all()
    for i, event in enumerate(events):
      if i == 0:
        continue
      try: 
        if event.tach_start != events[i-1].tach_end:
          print "Tach  Mismatch between %s and %s (start %s: %s, end %s: %s)!\n" % (event.creator_email, events[i-1].creator_email,
                                                        event.end_date, event.tach_start, events[i-1].start_date, events[i-1].tach_end)
          break
        else:
          exists, soup = check_for_and_get_event(event)
          if exists:
            # Consider auto-updating the event?
            pass
          else:
            upload_event(event)
      except (IndexError, ValueError) as e:
        raise Exception('Can\'t compare tachs: %r, %r, %r' % (e, event, events[i-1]))

def retrieve_files(service, folder_id):
  """Retrieve a list of File resources.
  Args:
    service: Drive API service instance.
  Returns:
    List of File resources.
  """
  result = []
  page_token = None
  while True:
    try:
      param = {}

      if page_token:
        param['pageToken'] = page_token

      files = service.children().list(folderId=folder_id, **param).execute()
      # files = service.files().list(**param).execute()

      result.extend(files['items'])
      page_token = files.get('nextPageToken')

      if not page_token:
        break
    except errors.HttpError, error:
      print 'An error occurred: %s' % error
      break
  return result

def print_metadata(service, file_id):
  """Print a file's metadata.
  Args:
    service: Drive API service instance.
    file_id: ID of the file to print metadata for.
  """
  try:
    file = service.files().get(fileId=file_id).execute()
    print 'Metadata: %s' % file
  except errors.HttpError, error:
    print 'An error occurred: %s' % error

def download_file(service, file_id):
  """Download a file's content.

  Args:
    service: Drive API service instance.
    drive_file: Drive File instance.

  Returns:
    File's content if successful, None otherwise.
  """
  file = service.files().get(fileId=file_id).execute()
  modified_date = file['modifiedDate']
  download_url = file['exportLinks']['text/html']
  print "url: " + download_url
  if download_url:
    resp, content = service._http.request(download_url)
    if resp.status == 200:
      #print 'Status: %s' % resp
      return modified_date, content
    else:
      print 'An error occurred: %s' % resp
      return None
  else:
    # The file doesn't have any content stored on Drive.
    return None

def query_events(calendar_service, calendar_id, timeMin):
  events = calendar_service.events().list(calendarId=calendar_id, orderBy='startTime', singleEvents=True,
                                          timeMin=timeMin).execute()
  if events['items']:
    return events['items'] 
  else:
    None

def generate_and_store_credentials(): 
  flow = flow_from_clientsecrets(get_full_path('client_secrets.json'),
                               scope='https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/calendar',
                               redirect_uri='urn:ietf:wg:oauth:2.0:oob'
                                 )
  auth_uri=flow.step1_get_authorize_url()
  # We've used the "installed" auth feature to get our code already. 
  json_data = open(get_full_path('code.json'))
  data = json.load(json_data)
  code = data['code']
  credentials = flow.step2_exchange(code)
  storage = Storage(get_full_path('credentials.secret'))
  storage.put(credentials)

def build_service(credentials, service_name='drive'):
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
  http = credentials.authorize(http)
  return build(service_name, version, http=http), http

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
      p.set_defaults()
      return p
  if args is None:
      args = sys.argv[1:]
  parser = parser or make_parser()
  opts = parser.parse_args(args)

  def update_db_events(events):
    for cal_event in events:
      updated_datetime = cal_event['updated']
      db_event=FlyingEvent.query.filter_by(event_id=cal_event['id']).first()
      # New post, add to DB
      if db_event == None:
         print "New post!"
         db_event=FlyingEvent(cal_event['id'], updated_datetime, cal_event)
         db.session.add(db_event)
      else:
        if db_event<updated_datetime:
          print "Updating post!"
          db_event.update_event(updated_datetime, cal_event)
        else:
          print 'Post already updated'
          if opts.refresh:
            db_event.update_event(updated_datetime, cal_event)
      db.session.commit()

  if not os.path.exists(get_full_path('credentials.secret')):
    generate_and_store_credentials()
  storage=Storage(get_full_path('credentials.secret'))
  credentials=storage.get()

  drive_service, drive_http=build_service(credentials)
  cal_service, cal_http=build_service(credentials, service_name='calendar')

  # Mooney spreadsheet
  mooney_spreadsheet='0AvS2F7wRovC4dEpmMEFGYnJVVWZpV1RTUzZLYk5UTnc'
  mooney_calendar='r86s1non6cr5dsmmjk38580ol4@group.calendar.google.com'
  calendar = cal_service.calendars().get(calendarId=mooney_calendar).execute()

  # A static time for which our calendar entries are well formatted.
  time_format = '%Y-%m-%dT%H:%M:%S'
  timeMin=datetime(2013,04,01,0,0,0, tzinfo=timezone(calendar['timeZone'])).strftime(time_format+'%z')
  events=query_events(cal_service, mooney_calendar, timeMin)
  update_db_events(events)


if __name__ == '__main__':
    sys.exit(main())
