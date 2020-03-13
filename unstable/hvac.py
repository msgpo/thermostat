"""
hvac.py -- A set of classes designed for a simple HVAC system.

To be a complete HVAC system, it should have a heating system, cooling system,
and a vent.  All of these need a thermostat to control all of these.

Each one of these elements have thier own class, and should be created as a
property of a HVAC object.

These classes are designed to be run with an Arduino running PyMata found at
https://github.com/MrYsLab/pymata-aio.  The main script can be run from any
machine that can interface with the said Arduino.
"""

import logging
import sys
import datetime

LOGGER = logging.getLogger("__main__.hvac.py")

__version__ = "0.2.0"

# HVAC is controlled by an Arduino board with PyMata installed
try:
	from pymata_aio.pymata3 import PyMata3
	from pymata_aio.constants import Constants
except ModuleNotFoundError as e:
	LOGGER.error("PyMata3 is required for use.  https://github.com/MrYsLab/pymata-aio")
	#sys.exit()

# MQTT is optional but recommended
try:
	import paho.mqtt.client as mqtt
	import paho.mqtt.publish as mqtt_pub
	MQTT_ENABLED = True
except ModuleNotFoundError:
	MQTT_ENABLED = False
	LOGGER.warning("Package paho-mqtt is not installed.  MQTT communication will be disabled")

class Thermostat:
	"""
	class Thermostat => The main control class for the HVAC object

	This class does everything from getting the temperature of the house, to
	publishing the results to a mqtt broker.

	This is where the "Smart Stuff" happens
	"""
	def __init__(self, board, mqtt=None, tempSettings=None):
		"""
		board => Only required argument.  It is an initiated Arduino board with PyMata.
		mqtt => Optional => A dictionary contaning all of the required settings to connect
			with a mqtt broker.
		tempSettings => Maybe shoud be required but optional for now. => A dictionary of
			times and conditions to modify the temperature to keep the area at.

		properties:

		board => Arduino PyMata board
		tempSettings => Dictionary of times to modify the temperature
		modes => AUTO or MANUAL => When in AUTO, all temperatures are automaticaly controlled.
			When in MANUAL, it will run the HVAC for 2 cycles at that setting and then return
			to AUTO mode.
		tempSensors => A list of temperature sensors to use for various inputs
		groups => A set of tempSensors that are grouped as one single ententy
		_mqtt => MQTT connection settings

		"""
		self.LOGGER = logging.getLogger("__main__.hvac.Thermostat")

		self.board = board
		self._mqtt = mqtt
		self.tempSettings = tempSettings

		self.modes = ["AUTO", "MANUAL"]
		self._mode = "AUTO"

		self.tempSensors = []
		self.groups = {}

		self._desiredTemp = None
		self._occupied = None

	@property
	def mode(self):
		return self._mode

	@mode.setter
	def mode(self, mode):
		if mode in self.modes and mode != self.mode:
			self._mode = mode
			self.LOGGER.info("Thermostat mode changed to {}".format(self.mode))
		else:
			self.LOGGER.warning("{} is not a valid mode for this Thermostat".format(mode))

	@property
	def desiredTemp(self):
		return self._desiredTemp

	@desiredTemp.setter
	def desiredTemp(self, temp):
		if temp:
			self.mode = "MANUAL"
			self._desiredTemp = temp
			return
		try:
			currnet = datetime.datetime.now()
			if currnet.month >= 11 or currnet.month <= 3:
				tempDict = self.tempSettings["WINTER"]
			elif currnet.month >= 7 or currnet.month <= 9:
				tempDict = self.tempSettings["SUMMER"]
			else:
				self._desiredTemp = None
				return
			startTemp = tempDict.pop("DEFAULT_TEMP")
			modList = []
			try:
				occupiedSettings = tempDict.pop("OCCUPIED_SETTINGS")
				if self.occupied:
					modList.extend(occupiedSettings["HOME"])
				else:
					modList.extend(occupiedSettings["AWAY"])
			except KeyError:
				pass
			for settingType in tempDict:
				modList.extend(tempDict[settingType].values())
			modTemp = 0
			for mlist in modList:
				if self.getbetweenTime([mlist[0], mlist[1]]):
					modTemp += mlist[2]
			self._desiredTemp = startTemp + modTemp

		except KeyError as e:
			self.LOGGER.info("No temp modifications")
			self._desiredTemp = temp

	@property
	def mqtt(self):
		return self._mqtt

	@mqtt.setter
	def mqtt(self, mqtt_variables):
		if MQTT_ENABLED:
			self._mqtt = mqtt_variables
		else:
			self._mqtt = None

	@property
	def occupied(self):
		return self._occupied

	@occupied.setter
	def occupied(self, homeList):
		if homeList:
			self._occupied = True
		else:
			self._occupied = False

	def addSensor(self, sensor):
		if sensor not in self.tempSensors:
			self.board.set_pin_mode(sensor.controlPin, Constants.ANALOG)
			self.tempSensors.append(sensor)
			self.LOGGER.info("Sensor {} with control pin {} added to Thermostat".format(sensor.name, sensor.controlPin))

	def createSensorGroup(self, groupName):
		groupName = groupName.upper()
		if groupName not in self.groups:
			self.groups[groupName] = []
			self.LOGGER.info("Group {} created".format(groupName))

	def addSensorToGroup(self, sensor, group):
		if group in self.groups:
			if sensor in self.tempSensors:
				if sensor not in self.groups[group]:
					self.groups[group].append(sensor)
					self.LOGGER.info("Sensor {} added to group {}".format(sensor.name, group))
				else:
					self.LOGGER.warning("Sensor {} is already in group {}".format(sensor.name, group))
			else:
				self.LOGGER.warning("You must add the sensor {} to the Thermostat before adding to a group".format(sensor.name))
		else:
			self.LOGGER.warning("Group {} does not exist to add a sensor to".format(group))

	def updateSensors(self):
		for sensor in self.tempSensors:
			sensor.tempC = self.board.analog_read(sensor.controlPin)
			self.LOGGER.debug("Updated sensor {}".format(sensor.name))

	def getTemp(self, area, tempFormat="F"):
		if area.upper() in self.groups:
			temp = 0
			for sensor in self.groups[area.upper()]:
				if tempFormat == "F":
					temp += sensor.tempF
				else:
					temp += sensor.tempC
			groupTemp = temp / len(self.groups[area.upper()])
			self.LOGGER.debug("{} temp is {}".format(area, groupTemp))
			return groupTemp

		for sensor in self.tempSensors:
			if area.upper() = sensor.name:
				if tempFormat == "F":
					temp = sensor.tempF
				else:
					temp = sensor.tempC
				self.LOGGER.debug("Sensor {}: {}".format(area, temp))
				return temp

		self.LOGGER.warning("No area {} in Thermostat sensors or groups".format(area.upper()))
		return None

	def publish(self):
		if MQTT_ENABLED and self.mqtt:
			# Publish each sensor temp first
			for sensor in self.tempSensors:
				temp = self.getTemp(sensor.name)
				topic = "/".join(self.mqtt["PATH"], sensor.name.lower())
				mqtt_pub.single(topic, payload=temp, qos=1, retain=True, hostname=self.mqtt["HOST"], port=int(self.mqtt["PORT"]), auth={"username": self.mqtt["USER"], "password": self.mqtt["PASSWORD"]})
			# Now publish the groups
			for area in self.groups:
				temp = self.getTemp(area)
				topic = "/".join(self.mqtt["PATH"], area.lower())
				mqtt_pub.single(topic, payload=temp, qos=1, retain=True, hostname=self.mqtt["HOST"], port=int(self.mqtt["PORT"]), auth={"username": self.mqtt["USER"], "password": self.mqtt["PASSWORD"]})
		else:
			self.LOGGER.warning("MQTT is either not enabled, or not setup correct")

	#def getTimeOfYear(self):
		#currnet = datetime.datetime.now()
		#if currnet.month >= 11 or currnet.month <= 3:
			#return "WINTER"
		#if currnet.month >= 7 or currnet.month <= 9:
			#return "SUMMER"
		#else:
			#return None

	def getBetweenTime(self, timeList):
		"""
		timeList => 2 - 4 digit string in 24 hr time format
				ex:		["startTime", "endTime"]
				ex:		["0600", "0930"] 6:00 am to 9:30 am
				ex:		["0", "0"] all 24 hours
		"""
		if int(timeList[0]) == 0 or int(timeList[1]) == 0:
			return True

		now = datetime.datetime.now()
		startHour = int(timeList[0][:2])
		startMinute = int(timeList[0][2:])
		endHour = int(timeList[1][:2])
		endMinute = int(timeList[1][2:])

		if now.hour >= startHour and now.minute >= startMinute:
			if now.hour <= endHour and now.minute < endMinute:
				return True
		return False

	#def setMod(self, modList):
		#"""
		#modList =>  A list of either tuples or lists with exactly 3 elements

				#[(startTime1, endTime1, modValue1), [startTime2, endTime2, modValue2]]
		#"""
		#modTemp = 0

		#for l in modList:
			#if self.getBetweenTime([l[0], l[1]]):
				#modTemp += l[2]

		#return modTemp

class Heater:
	def __init__(self, board, controlPins):
		"""
		board => A pymata instance passed from the HVAC

		controlPins => list of arduino pins to use with pymata
				[off, on]
		"""
		self.LOGGER = logging.getLogger("__main__.hvac.Heater")
		self.board = board
		self.controlPins = controlPins
		self._state = "OFF"

		for pin is self.controlPins:
			self.board.set_pin_mode(pin, Constants.OUTPUT)

	@property
	def state(self):
		return self._state

	@state.setter
	def state(self, onOff):
		if onOff.upper() == "ON":
			self._state = onOff
			self.turnOn()
		 if onOff.upper() == "OFF":
			 self._state = onOff
			 self.turnOff

	def turnOn(self):
		self.board.digital_write(self.controlPins[0], 1)
		self.board.sleep(0.1)
		self.board.digital_write(self.controlPins[0], 0)
		self.board.sleep(0.1)

	def turnOff(self):
		self.board.digital_write(self.controlPins[1], 1)
		self.board.sleep(0.1)
		self.board.digital_write(self.controlPins[1], 0)
		self.board.sleep(0.1)

class AirConditioner:
	def __init__(self, board, controlPins):
		"""
		board => A pymata instance passed from the HVAC

		controlPins => list of arduino pins to use with pymata
				[off, on]
		"""
		self.LOGGER = logging.getLogger("__main__.hvac.AirConditioner")
		self.board = board
		self.controlPins = controlPins
		self._state = "OFF"

		for pin is self.controlPins:
			self.board.set_pin_mode(pin, Constants.OUTPUT)

	@property
	def state(self):
		return self._state

	@state.setter
	def state(self, onOff):
		if onOff.upper() == "ON":
			self._state = onOff
			self.turnOn()
		 if onOff.upper() == "OFF":
			 self._state = onOff
			 self.turnOff

	def turnOn(self):
		self.board.digital_write(self.controlPins[0], 1)
		self.board.sleep(0.1)
		self.board.digital_write(self.controlPins[0], 0)
		self.board.sleep(0.1)

	def turnOff(self):
		self.board.digital_write(self.controlPins[1], 1)
		self.board.sleep(0.1)
		self.board.digital_write(self.controlPins[1], 0)
		self.board.sleep(0.1)

class Vent:
	def __init__(self, board, controlPins):
		"""
		controlPins => list of arduino pins to use with pymata
				[off, on]
		"""
		self.LOGGER = logging.getLogger("__main__.hvac.Vent")
		self.board = board
		self.controlPins = controlPins
		self._state = "OFF"

		for pin is self.controlPins:
			self.board.set_pin_mode(pin, Constants.OUTPUT)

	@property
	def state(self):
		return self._state

	@state.setter
	def state(self, onOff):
		if onOff.upper() == "ON":
			self._state = onOff
			self.turnOn()
		 if onOff.upper() == "OFF":
			 self._state = onOff
			 self.turnOff

	def turnOn(self):
		self.board.digital_write(self.controlPins[0], 1)
		self.board.sleep(0.1)
		self.board.digital_write(self.controlPins[0], 0)
		self.board.sleep(0.1)

	def turnOff(self):
		self.board.digital_write(self.controlPins[1], 1)
		self.board.sleep(0.1)
		self.board.digital_write(self.controlPins[1], 0)
		self.board.sleep(0.1)

class HVAC:
	"""
	class HVAC
		Controls a typical HVAC unit consisting of a heater, air conditioner,
		and a vent.

		You must add each object to the HVAC object for it to work
	"""
	def __init__(self, name, port=None):
		self.LOGGER = logging.getLogger("__main__.hvac.HVAC")
		if port:
			try:
				self.board = PyMata3(com_port=port)
			except Exception as e:
				self.LOGGER.error("Cannot connect to com port {}".format(port))
				#sys.exit()
		else:
			try:
				self.board = PyMata3()
			except Exception as e:
				self.LOGGER.error("Cannot connect to default com port")
				#sys.exit()

		self.heater = None
		self.ac = None
		self.vent = None
		self.thermostat = None

	def changeHeatState(self, state):
		self.heater.state = state

	def changeACState(self, state):
		self.ac.state = state

	def changeVentState(self, state):
		self.vent.state = state
