#!/usr/bin/python -u
###
# This file is part of Arduino Ciao
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# 
# Copyright 2015 Arduino Srl (http://www.arduino.org/)
# 
# authors:
# _giuseppe[at]arduino[dot]org
#
###

import io, os, sys, signal, serial
import logging, json
from threading import Thread
import time
import atexit

import settings
from utils import *
from ciaoconnector import CiaoConnector
import ciaoserver

#function to handle OS signals
def signal_handler(signum, frame):
	global logger
	global keepcycling
	logger.info("Received signal %d" % signum)
	keepcycling = False

#opening logfile
logger = get_logger("ciao")

#loading configuration for connectors
settings.load_connectors(logger)

#check if connectors have been actually loaded
if not "connectors" in settings.conf or len(settings.conf["connectors"]) == 0:
	logger.critical("No connector enabled, exiting.")
	sys.exit(1)

#creating shared dictionary
shd = {}

#start ciaoserver thread (to interact with connectors)
server = Thread(name="server", target=ciaoserver.init, args=(settings.conf,shd,))
server.daemon = True
server.start()

#we start MANAGED connectors after ciaoserver (so they can register properly)
for connector, connector_conf in settings.conf['connectors'].items():
	shd[connector] = CiaoConnector(connector, connector_conf)

	# connector must start after it has been added to shd,
	# it can register only if listed in shd
	shd[connector].start()

#TODO: maybe we can start another thread to control Ciao Core status

#variable to "mantain control" over while loop
keepcycling = True

#adding signals management
signal.signal(signal.SIGINT, signal_handler) #ctrl+c
signal.signal(signal.SIGHUP, signal_handler) #SIGHUP - 1
signal.signal(signal.SIGTERM, signal_handler) #SIGTERM - 15

baseports = ['/dev/ttyACM']
baud = 115200
s = None
for baseport in baseports :
	if s :
		break
	for i in xrange(0, 8) :
		try :
			port = baseport + str(i)
			s = serial.Serial(port, baud)
			logger.debug("Open serial port %s" % port)
			break
		except :
			s = None
			pass

while keepcycling:
	try:
		#reading from input device
		cmd = clean_command(s.readline())
	except serial.SerialException :
		keepcycling = False
		logger.warning("Disconnected (Serial exception)")
	except KeyboardInterrupt, e:
		logger.warning("SIGINT received")
	except IOError, e:
		logger.warning("Interrupted system call")
	else:
		if cmd:
			logger.debug("%s" % cmd)
			connector, action = is_valid_command(cmd)
			if connector == False:
				logger.warning("unknown command: %s" % cmd)
				out(s,-1, "unknown_command")
			elif connector == "ciao": #internal commands
				params = cmd.split(";",2)
				if len(params) != 3:
					out(s,-1, "unknown_command")
					continue
				if action == "r" and params[2] == "status": #read status
					out(s,1, "running")
				elif action == "w" and params[2] == "quit": #stop ciao
					out(s,1, "done")
					keepcycling = False
			elif not connector in settings.conf['connectors']:
				logger.warning("unknown connector: %s" % cmd)
				out(s,-1, "unknown_connector")
			else:
				shd[connector].run(s,action, cmd)

		# the sleep is really useful to prevent ciao to "cap" all CPU
		# this could be increased/decreased (keep an eye on CPU usage)
		time.sleep(0.01)

#stopping connectors (managed)
for name, connector in shd.items():
	logger.info("Sending stop signal to %s" % name)
	connector.stop()

logger.info("Exiting")
sys.exit(0)
