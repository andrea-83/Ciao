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
###

import logging,time
import socket, asyncore
import json

from ciaotools import CiaoThread

class RESTCiao(CiaoThread):
	# overriding native asyncore function to handle message received via socket
	def handle_read(self):
		#self.logger.debug("Handle READ")
		#start = time.time()
		data = self.recv(2048)
		# calling decode_multiple (from ciaoThread) to handle multiple string at once from Core
		for data_decoded in self.decode_multiple(data):
			if "status" in data_decoded:
				if self.write_pending:
					self.shd["requests"][data_decoded["checksum"]] = self.data_pending
					self.data_pending = None
					self.write_pending = False
				else:
					self.logger.warning("result msg but not write_pending: %s" % data)
			else:
				self.connector_queue.put(data_decoded)
				#roundtrip = time.time() - start
				#self.logger.debug("time read: %s" % roundtrip)

	# writable/handle_write are function useful ONLY 
	# if the connector offers communication from OUTSIDE WORLD to MCU
	def writable(self):
		if not self.shd["loop"]:
			raise asyncore.ExitNow('Connector is quitting!')
		if not self.ciao_queue.empty() and not self.write_pending:
			return True
		return False

	def handle_write(self):
		#self.logger.debug("Handle WRITE")
		#start = time.time()
		entry = self.ciao_queue.get()

		# we wait a feedback (status + checksum) from ciao
		self.write_pending = True
		self.data_pending = entry
		self.send(json.dumps(entry))
		#roundtrip = time.time() - start
		#self.logger.debug("time write: %s" % roundtrip)