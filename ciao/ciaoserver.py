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

import os, sys, logging
import socket, asyncore
import json

from utils import *

class CiaoHandler(asyncore.dispatcher_with_send):
	def __init__(self, sock, name, shm):
		asyncore.dispatcher_with_send.__init__(self, sock)
		self.name = name
		self.shm = shm
		self.shm[self.name].register()
		self.checksum = ""
		self.data = ""
		self.logger = logging.getLogger("ciao.handler." + self.name)
		self.logger.debug('Started')

	#this function must return true only if we have something
	# to write - through socket - to the ciao connector
	def writable(self):
		checksum, entry = self.shm[self.name].stash_get("out")
		if checksum:
			self.checksum = checksum
			self.data = entry
			return True

	def handle_read(self):
		message = self.recv(2048)
		message = message.rstrip()
		if message == "":
			self.logger.warning("Received empty message (IGNORED)")
			return
		self.logger.debug("handle_read (msg) - %s" % message)
		if message == "":
			return
		try:
			#TODO this must check if - inside hash - there is the key "data" (raiserror if not)
			entry = json.loads(message)
		except ValueError, e:
			self.logger.warning("String not empty but not JSON: %s" % message)
		else:
			if "checksum" in entry:
				self.shm[self.name].stash_put("result", entry['checksum'], entry['data'])
				checksum = entry['checksum']
			else:
				checksum = get_checksum(message, False)
				self.logger.debug("handle_read (checksum) - %s" % checksum)

				self.shm[self.name].stash_put("in", checksum, entry)
				
			# connector MUST receive a feedback from core
			result = {
				"status" : 1,
				"checksum": checksum
			}
			self.send(json.dumps(result))

	def handle_write(self):
		self.send(json.dumps(self.data))
		self.data = ""
		self.checksum = ""

	def handle_close(self):
		self.close()
		self.logger.debug('Closed')
		#notify to server that this connector has disconnected
		self.shm[self.name].unregister()

	def handle_error(self):
		nil, t, v, tbinfo = asyncore.compact_traceback()

		# sometimes a user repr method will crash.
		try:
			self_repr = repr(self)
		except:
			self_repr = '<__repr__(self) failed for object at %0x>' % id(self)

		self.logger.error('Uncaptured python exception %s (%s:%s %s)' % (self_repr, t, v, tbinfo))
		self.logger.error('Closing channel' % self.name)
		self.close()
		#self.close should trigger handle_close but it seems it doesn't (than we call it manually)
		self.handle_close()


class CiaoServer(asyncore.dispatcher):

	# default host to listen
	host = "localhost"
	# default port to listen
	port = 8900
	# max client to listen for
	backlog = 1

	# "bind" status
	# ready = False

	def __init__(self, conf, shm):
		asyncore.dispatcher.__init__(self)
		self.clients = []
		self.shm = shm
		self.logger = logging.getLogger("ciao.server")

		if "host" in conf['server']:
			self.host = conf['server']['host']
		if "port" in conf['server']:
			self.port = conf['server']['port']

		self.backlog = conf['backlog']

		while not self.prepare_socket():
			self.logger.debug("Waiting for bind retry")
			time.sleep(1)

	def prepare_socket(self):
		try:
			#creating server socket
			self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
			self.set_reuse_addr()

			self.bind((self.host, self.port))
		except Exception, e:
			self.logger.error("Problem creating %s socket: %s" % (__name__, e))

			# closing socket to retry in future
			self.close()
			return False
		else:
			self.listen(self.backlog)
			return True

	def handle_accept(self):
		pair = self.accept()
		if pair is not None:
			sock, addr = pair
			self.logger.info('Incoming connection from %s', repr(addr))

			#new client has to present itself (action:register)
			hello = sock.recv(1024)
			try:
				data = json.loads(hello)
				if not data['action'] or data['action'] != 'register' or not data['name']:
					self.logger.warning('New client not presented properly %s' % hello)
					sock.close()
				else:
					self.logger.info('Registering new connector with name %s' % data['name'])
					if not data['name'] in self.shm:
						self.logger.warning('No connectors enabled with name %s' % data['name'])
						sock.close()
					elif self.shm[data['name']].is_registered():
						self.logger.error('Connector %s already registered' % data['name'])
						sock.close()
					else:
						handler = CiaoHandler(sock, data['name'], self.shm)
						self.clients.append(handler)
			except ValueError, e:
				self.logger.error('Exception: new client not presented properly %s' % hello)
				sock.close()

	#function for debug purpose
	def broadcast_message(self, source_client, message):
		for c in self.clients:
			if c != source_client:
				c.send(message)

def init(conf, shm):
	server = CiaoServer(conf, shm)
	asyncore.loop(0.05)