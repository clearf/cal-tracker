#!/usr/bin/env python

# Web and google api
import httplib2
import os
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from apiclient import errors
from apiclient.discovery import build
from apiclient import errors

from ..db.common import BlogPost, db

# Utilities
import json

def get_full_path(file):
  return os.path.join(os.path.dirname(__file__), file)

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

def generate_and_store_credentials(): 
  flow = flow_from_clientsecrets(get_full_path('client_secrets.json'),
                               scope='https://www.googleapis.com/auth/drive.readonly',
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

def build_service(credentials):
  """Build a Drive service object.

  Args:
    credentials: OAuth 2.0 credentials.

  Returns:
    Drive service object.
  """
  http = httplib2.Http()
  http = credentials.authorize(http)
  return build('drive', 'v2', http=http), http

if __name__ == '__main__':
  #generate_and_store_credentials()
  storage=Storage(get_full_path('credentials.secret'))
  credentials=storage.get()

  service, http=build_service(credentials)
  # This is the "published" folder that contains our pubished posts.
  folder_id = '0B_S2F7wRovC4X2hralB6S3gtRmM'
  files = retrieve_files(service, folder_id)

  # My test file for consistency checking (which fails, btw)
  # print download_file(service, '1ofKJJh9t5LUPU_XLWLg4fL-NZWfqA4Vs3N-maUAlBPE')
  # print_metadata(service, '1ofKJJh9t5LUPU_XLWLg4fL-NZWfqA4Vs3N-maUAlBPE')
  for file in files:
    modified_date, content = download_file(service, file['id'])
    post=BlogPost.query.filter_by(file_id=file['id']).first()
    # New post, add to DB
    if post == None:
      print "New post!"
      post=BlogPost(file['id'], modified_date, content)
      db.session.add(post)
    else:
      if post<modified_date:
        print "Updating post!"
        post.update_post(modified_date, content)
      else:
        print 'Post already updated'
        # XXX remove this forced update later
        post.update_post(modified_date, content)
    db.session.commit()
    print unicode(post)

# Database will have;
# ID is the google drive ID -- a unique string
# The same logic as BlogPost to parse the HTML from drive.
# Modify-date to check if things have been updated. If they have,
# we run the parsing logic again.

# Workflow: 
# So, every N minutes, we'll run this program, loop throught the files in this directory,
# check for new files (which we create a new entry and add)
