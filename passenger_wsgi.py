# -*- coding: utf-8 -*-

"""Passenger mode"""
import sys, os

INTERP = os.path.join(os.environ['HOME'], 'cal-tracker', 'prod', 'bin', 'python')
if sys.executable != INTERP:
        os.execl(INTERP, INTERP, *sys.argv)
sys.path.append(os.getcwd())

#activate_this = os.path.join(os.environ['HOME'], 'cal-tracker', 'prod', 'bin', 'activate_this.py')
#execfile(activate_this, dict(__file__=activate_this))

from app import app as application
