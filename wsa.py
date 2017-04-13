#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  wsa.py
#  
#  Copyright 2017 Giorgio Ladu
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#  
# weewx driver that reads data from Arduino 
# weather station connected to internet

### USAGE
##  Copy this file in weewx/drivers/ path
##  Used library urllib2 and json
###

from __future__ import with_statement
import syslog
import time
import urllib2
import json

import weewx.drivers
import weewx.wxformulas

DRIVER_NAME = 'WSA'
DRIVER_VERSION = "0.5"
DEFAULT_TCP_ADDR = '192.168.0.116'
DEFAULT_FILE = 'wxdata'
DEFAULT_TCP_PORT = 80
DEFAULT_POLL = 120 #update 2 min

DEBUG_RAW = 1

def logmsg(dst, msg):
    syslog.syslog(dst, 'wsa: %s' % msg)

def logdbg(msg):
    logmsg(syslog.LOG_DEBUG, msg)

def loginf(msg):
    logmsg(syslog.LOG_INFO, msg)

def logerr(msg):
    logmsg(syslog.LOG_ERR, msg)


def _get_as_float(s, multiplier=None):
	v = None
	try:
		v = float(s)
		if multiplier is not None:
			v *= multiplier
	except ValueError, e:
			logerr("cannot read value for '%s': %s" % (s, e))
	return v

def loader(config_dict, engine):
	return WSA(**config_dict[DRIVER_NAME])

class WSA(weewx.drivers.AbstractDevice):
	"""weewx driver that communicates with an Arduino weather station.

	model: Which station model is this?
	[Optional. Default is 'Arduino']

	max_tries: How often to retry communication before giving up.
	[Optional. Default is 4]
	
	host: Arduino host ip 
	[Optional. Default is 192.168.4.1]
	
	host_port: Arduino http server port 
	[Optional. Default is 80]
	
	path: file whereis stored data in json format.
	[Optional. Default is 'wxdata']
	
	NOTE:
	* the URL of data is similar to 
	http://192.168.0.116:80/wxdata
	
	* usUnits are in METRICS
	* json weather pokets format:
	{
	"dateTime" : 1491324468, //RTC DS3231
	"outTemp" : 17.10, //sensirion SHT15
	"outHumidity" : 50.00, //sensirion SHT15
	"leafTemp1" : 17.22, //mh-rd + DHT22
	"pressure" : 1016.10, //Bosch DIGITAL PRESSURE SENSORBMP280
	"rain" : 0.00,
	"rainRate" : 0.00,
	"dayRain" : 0.00, //Arduino Average library
	"leafWet1" : 0, //mh-rd + DHT22
	"soilMoist1" : 0, //YL-69
	"heatindex" : 16.30,
	"lux" : 120988, //BH1750 min. 0.11 lx, max. 100000 lx
	"UV" : 1.99, //
	"windDir" : 180, //ADS1115 Resolution 16 Bits connect to wind vane 
	"windSpeed" : 0.00, //ADS1015 connect to anemometer. A wind speed of 2.4km/h causes the switch to close once per second. 
	"windGust" : 0.00, // Arduino Average library
	"windGustDir" : 180 // Arduino Average library
	}
	
	* weather packet send at weewx is in the format:
	_packet[name_sensor] = value 
	for name of sensors see weewx doc file
	value are stored in float
	
	* dateTime is in epoch unix time, in UTC ( for prevent problem by
	change of daylight saving time to winter time )
	
	"""
	
	def __init__(self, **stn_dict):
		self.model = stn_dict.get('model', 'Arduino')
		# where to find the data file
		self.host = stn_dict.get('host', DEFAULT_TCP_ADDR)
		self.host_port = str(stn_dict.get('host_port', DEFAULT_TCP_PORT))       
		# where to find the data file
		self.path = stn_dict.get('path', DEFAULT_FILE )
		# how often to poll the weather data file, seconds
		self.poll_interval = int(stn_dict.get('polling_interval', DEFAULT_POLL))
		# These come from the configuration dictionary:
		self.max_tries = int(stn_dict.get('max_tries', 4))
		self.device_id = stn_dict.get('device_id', 'Kronos')
		
		# mapping from variable names to weewx names
		# not used 
		self.label_map = stn_dict.get('label_map', {})
		  
		if DEBUG_RAW:
			loginf('driver version is %s' % DRIVER_VERSION)
			loginf("Host %s" % self.host)
			loginf("Port %s" % self.host_port)
			loginf("file %s" % self.path)
			loginf("polling interval is %s" % self.poll_interval)
			loginf('label map is %s' % self.label_map)

	def genLoopPackets(self):
		online = self.max_tries
		url='http://'+self.host+':'+self.host_port+'/'+self.path		
		buf=''
		_packet = {#'dateTime': int(time.time() + 0.5),
                          'usUnits': weewx.METRIC}
		data = {}
		
		while online: # read whatever values we can get from the file            
			try:
				if DEBUG_RAW:
					loginf('Url is %s' % url)
				req = urllib2.Request(url)
				response = urllib2.urlopen(req)
				buf = response.read()				
				response.close()
			except Exception, e:
				logerr("read failed: %s" % e)

			if DEBUG_RAW:
				loginf('RAW DATA: %s' % buf)

			if len(buf) > 0 :
				data = json.loads(buf)				
				for key, value in data.items():
					_packet[str(key)] = _get_as_float(value)
				_packet['hourRain'] = _get_as_float(_packet['rainRate'])						
				_packet['inTemp'] = _get_as_float(_packet['outTemp'], 1.2)
				_packet['inHumidity'] = _get_as_float(_packet['outHumidity'], 1.2)
				#calc radiation from lux
				#reports radiation with a lux-to-W/m^2
				# multiplier of 0.001464. 
				_packet['radiation'] = _get_as_float(_packet['lux'], 0.001464)
				T = _packet['outTemp']
				R = _packet['outHumidity']
				W = _packet['windSpeed']
				_packet['dewpoint']  = weewx.wxformulas.dewpointF(T, R)
				_packet['windchill'] = weewx.wxformulas.windchillF(T, W)
				
				if _packet['windSpeed'] == 0:
					_packet['windSpeed'] = None
					_packet['windDir'] = None
				if _packet['windGust'] == 0:
					_packet['windGust'] = None
					_packet['windGustDir'] = None

				if DEBUG_RAW:
					loginf('RAW DATA in _packet')
					for key, value in _packet.items():
						loginf('Key %s value %s' % (key, value))
			else:
				logerr("cannot read value") 
				logerr('Buf size %s' % len(buf)) 
				_packet['dateTime'] = int(time.time() +0.5)
				online -= 1
				
			yield _packet
			time.sleep(self.poll_interval)

	@property
	def hardware_name(self):
		return DRIVER_NAME

if __name__ == "__main__":
	import weeutil.weeutil
	station = WSA()
	for packet in station.genLoopPackets():
		print weeutil.weeutil.timestamp_to_string(packet['dateTime']), packet
