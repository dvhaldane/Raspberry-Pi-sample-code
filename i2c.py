#!/usr/bin/python

import io         # used to create file streams
from io import open
import fcntl      # used to access I2C parameters like addresses

import time       # used for sleep delay and timestamps
import string     # helps parse strings
import mysql.connector 
import os	  #use os to get environment variable for aquarium

class AtlasI2C:
	long_timeout = 1.5         	# the timeout needed to query readings and calibrations
	short_timeout = .5         	# timeout for regular commands
	default_bus = 1         	# the default bus for I2C on the newer Raspberry Pis, certain older boards use bus 0
	default_address = 98     	# the default address for the sensor
	current_addr = default_address

	def __init__(self, address=default_address, bus=default_bus):
		# open two file streams, one for reading and one for writing
		# the specific I2C channel is selected with bus
		# it is usually 1, except for older revisions where its 0
		# wb and rb indicate binary read and write
		self.file_read = io.open("/dev/i2c-"+str(bus), "rb", buffering=0)
		self.file_write = io.open("/dev/i2c-"+str(bus), "wb", buffering=0)

		# initializes I2C to either a user specified or default address
		self.set_i2c_address(address)

	def set_i2c_address(self, addr):
		# set the I2C communications to the slave specified by the address
		# The commands for I2C dev using the ioctl functions are specified in
		# the i2c-dev.h file from i2c-tools
		I2C_SLAVE = 0x703
		fcntl.ioctl(self.file_read, I2C_SLAVE, addr)
		fcntl.ioctl(self.file_write, I2C_SLAVE, addr)
		self.current_addr = addr

	def write(self, cmd):
		# appends the null character and sends the string over I2C
		cmd += "\00"
		self.file_write.write(cmd.encode('latin-1'))

	def read(self, num_of_bytes=31):
		# reads a specified number of bytes from I2C, then parses and displays the result
		res = self.file_read.read(num_of_bytes)         # read from the board
		if type(res[0]) is str:					# if python2 read
			response = [i for i in res if i != '\x00']
			if ord(response[0]) == 1:             # if the response isn't an error
				# change MSB to 0 for all received characters except the first and get a list of characters
				# NOTE: having to change the MSB to 0 is a glitch in the raspberry pi, and you shouldn't have to do this!
				char_list = list(map(lambda x: chr(ord(x) & ~0x80), list(response[1:])))
				return ''.join(char_list)     # convert the char list to a string and returns it
			else:
				return "ERR " + str(ord(response[0]))
				
		else:									# if python3 read
			if res[0] == 1: 
				# change MSB to 0 for all received characters except the first and get a list of characters
				# NOTE: having to change the MSB to 0 is a glitch in the raspberry pi, and you shouldn't have to do this!
				char_list = list(map(lambda x: chr(x & ~0x80), list(res[1:])))
				return ''.join(char_list)     # convert the char list to a string and returns it
			else:
				return "ERR " + str(res[0])

	def query(self, string):
		# write a command to the board, wait the correct timeout, and read the response
		self.write(string)

		# the read and calibration commands require a longer timeout
		if((string.upper().startswith("R")) or
			(string.upper().startswith("CAL"))):
			time.sleep(self.long_timeout)
		elif string.upper().startswith("SLEEP"):
			return "sleep mode"
		else:
			time.sleep(self.short_timeout)

		return self.read()

	def close(self):
		self.file_read.close()
		self.file_write.close()

	def list_i2c_devices(self):
		prev_addr = self.current_addr # save the current address so we can restore it after
		i2c_devices = []
		for i in range (0,128):
			try:
				self.set_i2c_address(i)
				self.read(1)
				i2c_devices.append(i)
			except IOError:
				pass
		self.set_i2c_address(prev_addr) # restore the address we were using
		return i2c_devices
	
class DB():
	connection = none
	
	def __init__(self):
		connect()
				
	def checkConn(self):
	    sq = "SELECT NOW()"
	    try:
		connection.cursor.execute( sq )
	    except pymysql.Error as e:
		if e.errno == 2006:
		    return self.connect()
		else:
		    print ( "No connection with database." )
		    return False
		
	def connect(hostname="localhost", username="pi", userpass="raspberry", db="reefpi"):
		connection = mysql.connector.connect(
		  host=hostname,
		  user=username,
		  passwd=userpass,
		  database=db
		)
		
#start script in GNU screen using command: screen -dm bash -c 'python your_script.py'		
def main():
	#get aquarium id
	aquariumid = os.environ['AQUARIUM_ID']
	
	#setup db
	db = DB()
			
	device = AtlasI2C() 	# creates the I2C port object, specify the address or bus if necessary
	sensors = {}	# holds list of valid Atlas Scientific sensor types and their corresponding addresses as dict(type, address)
	valid_sensor_types = ["pH","RTD"]
	
	#get all Atlas Scientific I2C devices
	devices = device.list_i2c_devices()
	for i in range(len (devices)):
		#set address of device
		device.set_i2c_address(devices[i])
		print("I2C address set to " + str(devices[i]))
		
		#get device type
		devicetype = string.split(device.query("I"), ",")[1]
		print("Device type is: " + devicetype + " for address " + devices[i])
		
		#if sensor is a valid Atlas Scientific device, add it to the list of sensors
		if (devicetype in valid_sensor_types):
			sensors.update({devicetype : int(devices[i])})
			
	try:
		while True:
			
			#keep db connection alive
			if (db.checkConn()):
				Print("DB is connected")
			else:
				Print("DB is not connected")
			
			#Do temp reading
			tempaddress = sensors.get('RTD')
			if (tempaddress is None):
				print("No temperature sensor available. " + temperature)
				break
			device.set_i2c_address(int(tempaddress))
			temperature = device.query("R")
			
			if ("ERR" in temperature):
				print("Temperature reading has failed. " + temperature)
				#TODO - warn that temperature reading has errored
			else:
				#send temperature to DB	
				sql = """INSERT INTO SENSOR_DATA (SENSOR_TYPE, SENSOR_ADDRESS, SENSOR_VALUE, AQUARIUM_ID) 
				VALUES (%s, %d, %d, %d)"""
				val = ("RTD", tempaddress, float(temperature), aquariumid)
				db.connection.cursor.execute(sql, val)
				db.connection.commit()
				
				#Do ph Reading
				phaddress = sensors.get('pH')
				#stop reading if no ph sensor available
				if (phaddress is None):
					print("No ph sensor available. " + temperature)
	       			else:
					device.set_i2c_address(int(phaddress))
					ph = device.query("RT," + str(temperature))

					if ("ERR" in ph):
						print("pH reading has failed. " + ph)
					else:
						sql = """INSERT INTO SENSOR_DATA (SENSOR_TYPE, SENSOR_ADDRESS, SENSOR_VALUE, AQUARIUM_ID) 
						VALUES (%s, %d, %d, %d)"""
						val = ("pH", phaddress, float(ph), aquariumid)
						db.connection.cursor.execute(sql, val)
						db.connection.commit()					
			time.sleep(3)	
	except KeyboardInterrupt: 		# catches the ctrl-c command, which breaks the loop above
		print("Continuous polling stopped")
			
if __name__ == '__main__':
	main()

