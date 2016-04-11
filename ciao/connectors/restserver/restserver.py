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

import os, sys, signal, asyncore, socket, time
from thread import *
import json, logging
from Queue import Queue
import ciaotools

from restserverciao import RESTserverCiao

# function to handle SIGHUP/SIGTERM

def restserver_handler(conn, shd,logger):

	message = conn.recv(1024)
	logger.debug("Message %s" % message)
	reply = ""
	if message != "" :
	 	entry = {"data" : [str(message).rstrip('\r\n')]}
	 	socket_queue.put(entry)
		entry = rest_queue.get()
		if entry['type'] == "response":
			original_checksum = entry["source_checksum"]
			if not original_checksum in shd["requests"]:
				logger.warning("Received response to unknown checksum %s" % original_checksum)
			original_message = shd["requests"][original_checksum]
			reply = str(entry['data'][0])
			logger.debug("data send %s" % reply)
	conn.send(reply+'\r\n')
	conn.close()			

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
json_conf = open(shd["basepath"]+"restserver.json.conf").read()
shd["conf"] = json.loads(json_conf)
#init log

logger = ciaotools.get_logger("restserver", logconf=shd["conf"], logdir=shd["basepath"])

#forking to make process standalone
try:
	pid = os.fork()
	if pid > 0:
		# Save child pid to file and exit parent process
		runfile = open("/var/run/restserver-ciao.pid", "w")
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

ciaoclient = RESTserverCiao(shd, rest_queue, socket_queue)
ciaoclient.start()

try:
	HOST = shd["conf"]["params"]["host"]   
	PORT = shd["conf"]["params"]["port"] # Luci port
	s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	s.settimeout(10)
	s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	try:
		s.bind((HOST, PORT))
	except socket.error as msg:
		logger.error('Bind failed. Error Code : '+ str(msg[0]) +' Message ' + msg[1])
		sys.exit()	 
	#Start listening on socket
	logger.info("REST server connector started")
	s.listen(10)
	while shd["loop"] :
		conn, addr = s.accept()
		start_new_thread(restserver_handler ,(conn, shd,logger,))
		#restserver_handler (conn, shd,logger)

except Exception, e:
	s.close()
	logger.info("Exception while creating REST server: %s" % e)
	sys.exit(1)

else:
	s.close()
	logger.info("REST server connector is closing")
	sys.exit(0)
