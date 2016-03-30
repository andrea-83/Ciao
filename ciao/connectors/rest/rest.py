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
# _andrea[at]arduino[dot]org
# _giuseppe[at]arduino[dot]org
# 
#
###

import os, sys, signal,time, httplib
from thread import *
import json, logging
from Queue import Queue
import ciaotools

from restciao import RESTCiao

# function to handle SIGHUP/SIGTERM

def http_request(url, method, data, chk):

	try:
		conn = httplib.HTTPConnection(url);
		conn.request(method, data)	
		handler_conn = conn;
		response = conn.getresponse()
		data = response.read()
		conn.close()
		entry = {"checksum": chk, "data" : [str(response.status),str(data)]}
		logger.info("Request answer: %s" % data)
	except Exception,e:
		conn.close()
		entry = {"checksum": chk, "data" : [str("404"),str(e.strerror)]}

	socket_queue.put(entry)

def signal_handler(signum, frame):
	global logger
	logger.info("SIGNAL CATCHED %d" % signum)
	global shd
	shd["loop"] = False

#shared dictionary
shd = {}
shd["loop"] = True
shd["basepath"] = os.path.dirname(os.path.abspath(__file__)) + os.sep


#read configuration
#TODO
# verify configuration is a valid JSON
json_conf = open(shd["basepath"]+"rest.json.conf").read()
shd["conf"] = json.loads(json_conf)
#init log

logger = ciaotools.get_logger("rest", logconf=shd["conf"], logdir=shd["basepath"])

#forking to make process standalone
try:
	pid = os.fork()
	if pid > 0:
		# Save child pid to file and exit parent process
		runfile = open("/var/run/rest-ciao.pid", "w")
		runfile.write("%d" % pid)
		runfile.close()
		sys.exit(0)

except OSError, e:
	logger.critical("Fork failed")
	sys.exit(1)

rest_queue = Queue()
socket_queue = Queue()

signal.signal(signal.SIGINT, signal.SIG_IGN) #ignore SIGINT(ctrl+c)
signal.signal(signal.SIGHUP, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

shd["requests"] = {}

ciaoclient = RESTCiao(shd, rest_queue, socket_queue)
ciaoclient.start()

while shd["loop"] :
	#logger.info("dentro ciclo while")
	if not rest_queue.empty():
		entry = rest_queue.get()
		logger.info("Entry %s" % entry)

		# if entry received from ciao is an "out" message
		if entry['type'] == "result":

			chk = str(entry['checksum'])
			if not chk:
				logger.warning("Missing checksum param, dropping message")
				continue
			logger.debug("Checksum: %s" % chk)

			url = str(entry['data'][0])
			if not url:
				logger.warning("Missing stream param, dropping message")
				continue

			data = str(entry['data'][1])
			if not data:
				logger.warning("Missing data param, dropping message")
				continue
			logger.debug("Data: %s" % data)

			if (len(entry['data']) > 2):
				method = str(entry['data'][2])
				if not method:
					logger.warning("Missing method param, dropping message")
					continue
				logger.debug("Key: %s" % method)
			else:
				method = "GET"

			http_request(url, method, data, chk)

		else:
			continue

	# the sleep is really useful to prevent ciao to cap all CPU
	# this could be increased/decreased (keep an eye on CPU usage)
	# time.sleep is MANDATORY to make signal handlers work (they are synchronous in python)
	time.sleep(0.01)

logger.info("REST connector is closing")
sys.exit(0)
