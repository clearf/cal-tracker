#!/home/clearf/python/bin/python
import sys, os

activate_this = os.path.join(os.environ['HOME'], 'cal-tracker', 'prod', 'bin', 'activate_this.py') 
execfile(activate_this, dict(__file__=activate_this)) 

from app.google.google_client import main

if __name__ == '__main__':
  sys.exit(main())
