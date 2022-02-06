# v1.1 alpha

import random
import logging
import os
import io
import json
import csv
import subprocess
from subprocess import PIPE
import ipaddress
from ipaddress import IPv4Address, IPv6Address
import time
from datetime import date, datetime
from ispConfig import fqOrCAKE, upstreamBandwidthCapacityDownloadMbps, upstreamBandwidthCapacityUploadMbps, defaultClassCapacityDownloadMbps, defaultClassCapacityUploadMbps, interfaceA, interfaceB, shapeBySite, enableActualShellCommands, runShellCommandsAsSudo
import collections

def shell(command):
	if enableActualShellCommands:
		if runShellCommandsAsSudo:
			command = 'sudo ' + command
		commands = command.split(' ')
		print(command)
		proc = subprocess.Popen(commands, stdout=subprocess.PIPE)
		for line in io.TextIOWrapper(proc.stdout, encoding="utf-8"):  # or another encoding
			print(line)
	else:
		print(command)
		
def clearPriorSettings(interfaceA, interfaceB):
	if enableActualShellCommands:
		shell('tc filter delete dev ' + interfaceA)
		shell('tc filter delete dev ' + interfaceA + ' root')
		shell('tc qdisc delete dev ' + interfaceA + ' root')
		shell('tc qdisc delete dev ' + interfaceA)
		shell('tc filter delete dev ' + interfaceB)
		shell('tc filter delete dev ' + interfaceB + ' root')
		shell('tc qdisc delete dev ' + interfaceB + ' root')
		shell('tc qdisc delete dev ' + interfaceB)

def refreshShapers():
	tcpOverheadFactor = 1.09

	# Load Devices
	devices = []
	with open('Shaper.csv') as csv_file:
		csv_reader = csv.reader(csv_file, delimiter=',')
		next(csv_reader)
		for row in csv_reader:
			deviceID, ParentNode, mac, hostname,ipv4, ipv6, downloadMin, uploadMin, downloadMax, uploadMax = row
			ipv4 = ipv4.strip()
			ipv6 = ipv6.strip()
			if ParentNode == "":
				ParentNode = "none"
			ParentNode = ParentNode.strip()
			thisDevice = {
			  "id": deviceID,
			  "mac": mac,
			  "ParentNode": ParentNode,
			  "hostname": hostname,
			  "ipv4": ipv4,
			  "ipv6": ipv6,
			  "downloadMin": round(int(downloadMin)*tcpOverheadFactor),
			  "uploadMin": round(int(uploadMin)*tcpOverheadFactor),
			  "downloadMax": round(int(downloadMax)*tcpOverheadFactor),
			  "uploadMax": round(int(uploadMax)*tcpOverheadFactor),
			  "qdisc": '',
			}
			devices.append(thisDevice)
	
	#Load network heirarchy
	with open('network.json', 'r') as j:
		network = json.loads(j.read())
	
	#Clear Prior Settings
	clearPriorSettings(interfaceA, interfaceB)

	# Find queues available
	queuesAvailable = 0
	path = '/sys/class/net/' + interfaceA + '/queues/'
	directory_contents = os.listdir(path)
	print(directory_contents)
	for item in directory_contents:
		if "tx-" in str(item):
			queuesAvailable += 1
			
	# For VMs, must reduce queues if more than 9, for some reason
	if queuesAvailable > 9:
		command = 'grep -q ^flags.*\ hypervisor\  /proc/cpuinfo && echo "This machine is a VM"'
		try:
			output = subprocess.check_output(command, stderr=subprocess.STDOUT, shell=True).decode()
			success = True 
		except subprocess.CalledProcessError as e:
			output = e.output.decode()
			success = False
		if "This machine is a VM" in output:
			queuesAvailable = 9

	# XDP-CPUMAP-TC
	shell('./xdp-cpumap-tc/bin/xps_setup.sh -d ' + interfaceA + ' --default --disable')
	shell('./xdp-cpumap-tc/bin/xps_setup.sh -d ' + interfaceB + ' --default --disable')
	shell('./xdp-cpumap-tc/src/xdp_iphash_to_cpu --dev ' + interfaceA + ' --lan')
	shell('./xdp-cpumap-tc/src/xdp_iphash_to_cpu --dev ' + interfaceB + ' --wan')
	shell('./xdp-cpumap-tc/src/xdp_iphash_to_cpu_cmdline --clear')
	shell('./xdp-cpumap-tc/src/tc_classify --dev-egress ' + interfaceA)
	shell('./xdp-cpumap-tc/src/tc_classify --dev-egress ' + interfaceB)

	# Create MQ
	thisInterface = interfaceA
	shell('tc qdisc replace dev ' + thisInterface + ' root handle 7FFF: mq')
	for queue in range(queuesAvailable):
		shell('tc qdisc add dev ' + thisInterface + ' parent 7FFF:' + str(queue+1) + ' handle ' + str(queue+1) + ': htb default 2')
		shell('tc class add dev ' + thisInterface + ' parent ' + str(queue+1) + ': classid ' + str(queue+1) + ':1 htb rate '+ str(upstreamBandwidthCapacityDownloadMbps) + 'mbit ceil ' + str(upstreamBandwidthCapacityDownloadMbps) + 'mbit')
		shell('tc qdisc add dev ' + thisInterface + ' parent ' + str(queue+1) + ':1 ' + fqOrCAKE)
		# Default class - traffic gets passed through this limiter with lower priority if not otherwise classified by the Shaper.csv
		# Only 1/4 of defaultClassCapacity is guarenteed (to prevent hitting ceiling of upstream), for the most part it serves as an "up to" ceiling.
		# Default class can use up to defaultClassCapacityDownloadMbps when that bandwidth isn't used by known hosts.
		shell('tc class add dev ' + thisInterface + ' parent ' + str(queue+1) + ':1 classid ' + str(queue+1) + ':2 htb rate ' + str(defaultClassCapacityDownloadMbps/4) + 'mbit ceil ' + str(defaultClassCapacityDownloadMbps) + 'mbit prio 5')
		shell('tc qdisc add dev ' + thisInterface + ' parent ' + str(queue+1) + ':2 ' + fqOrCAKE)
	
	thisInterface = interfaceB
	shell('tc qdisc replace dev ' + thisInterface + ' root handle 7FFF: mq')
	for queue in range(queuesAvailable):
		shell('tc qdisc add dev ' + thisInterface + ' parent 7FFF:' + str(queue+1) + ' handle ' + str(queue+1) + ': htb default 2')
		shell('tc class add dev ' + thisInterface + ' parent ' + str(queue+1) + ': classid ' + str(queue+1) + ':1 htb rate '+ str(upstreamBandwidthCapacityUploadMbps) + 'mbit ceil ' + str(upstreamBandwidthCapacityUploadMbps) + 'mbit')
		shell('tc qdisc add dev ' + thisInterface + ' parent ' + str(queue+1) + ':1 ' + fqOrCAKE)
		# Default class - traffic gets passed through this limiter with lower priority if not otherwise classified by the Shaper.csv.
		# Only 1/4 of defaultClassCapacity is guarenteed (to prevent hitting ceiling of upstream), for the most part it serves as an "up to" ceiling.
		# Default class can use up to defaultClassCapacityUploadMbps when that bandwidth isn't used by known hosts.
		shell('tc class add dev ' + thisInterface + ' parent ' + str(queue+1) + ':1 classid ' + str(queue+1) + ':2 htb rate ' + str(defaultClassCapacityUploadMbps/4) + 'mbit ceil ' + str(defaultClassCapacityUploadMbps) + 'mbit prio 5')
		shell('tc qdisc add dev ' + thisInterface + ' parent ' + str(queue+1) + ':2 ' + fqOrCAKE)
	print()

	#Establish queue counter
	currentQueueCounter = 1
	queueMinorCounterDict = {}
	# :1 and :2 are used for root and default classes, so start each queue's counter at :3
	for queueNum in range(queuesAvailable):
		queueMinorCounterDict[queueNum+1] = 3

	devicesShaped = []
	#Parse network.json. For each tier, create corresponding HTB and leaf classes
	def traverseNetwork(data, depth, major, minor, queue, parentClassID):
		tabs = '   ' * depth
		for elem in data:
			print(tabs + elem)
			elemClassID = str(major) + ':' + str(minor)
			elemDownload = data[elem]['downloadBandwidthMbps']
			elemUpload = data[elem]['uploadBandwidthMbps']
			print(tabs + "Download:  " + str(elemDownload) + " Mbps")
			print(tabs + "Upload:    " + str(elemUpload) + " Mbps")
			print(tabs, end='')
			shell('tc class add dev ' + interfaceA + ' parent ' + parentClassID + ' classid ' + str(minor) + ' htb rate '+ str(round(elemDownload/4)) + 'mbit ceil '+ str(round(elemDownload)) + 'mbit prio 3') 
			print(tabs, end='')
			shell('tc qdisc add dev ' + interfaceA + ' parent ' + str(major) + ':' + str(minor) + ' ' + fqOrCAKE)
			print(tabs, end='')
			shell('tc class add dev ' + interfaceB + ' parent ' + parentClassID + ' classid ' + str(minor) + ' htb rate '+ str(round(elemUpload/4)) + 'mbit ceil '+ str(round(elemUpload)) + 'mbit prio 3') 
			print(tabs, end='')
			shell('tc qdisc add dev ' + interfaceB + ' parent ' + str(major) + ':' + str(minor) + ' ' + fqOrCAKE)
			print()
			minor += 1
			for device in devices:
				if elem == device['ParentNode']:
					maxDownload = min(device['downloadMax'],elemDownload)
					maxUpload = min(device['uploadMax'],elemUpload)
					minDownload = min(device['downloadMin'],maxDownload)
					minUpload = min(device['uploadMin'],maxUpload)
					print(tabs + '   ' + device['hostname'])
					print(tabs + '   ' + "Download:  " + str(minDownload) + " to " + str(maxDownload) + " Mbps")
					print(tabs + '   ' + "Upload:    " + str(minUpload) + " to " + str(maxUpload) + " Mbps")
					print(tabs + '   ', end='')
					shell('tc class add dev ' + interfaceA + ' parent ' + elemClassID + ' classid ' + str(minor) + ' htb rate '+ str(minDownload) + 'mbit ceil '+ str(maxDownload) + 'mbit prio 3')
					print(tabs + '   ', end='')
					shell('tc qdisc add dev ' + interfaceA + ' parent ' + str(major) + ':' + str(minor) + ' ' + fqOrCAKE)
					print(tabs + '   ', end='')
					shell('tc class add dev ' + interfaceB + ' parent ' + elemClassID + ' classid ' + str(minor) + ' htb rate '+ str(minUpload) + 'mbit ceil '+ str(maxUpload) + 'mbit prio 3') 
					print(tabs + '   ', end='')
					shell('tc qdisc add dev ' + interfaceB + ' parent ' + str(major) + ':' + str(minor) + ' ' + fqOrCAKE)
					if device['ipv4']:
						parentString = str(major) + ':'
						flowIDstring = str(major) + ':' + str(minor)
						print(tabs + '   ', end='')
						shell('./xdp-cpumap-tc/src/xdp_iphash_to_cpu_cmdline --add --ip ' + device['ipv4'] + ' --cpu ' + str(queue-1) + ' --classid ' + flowIDstring)
						device['qdisc'] = flowIDstring
						if device['hostname'] not in devicesShaped:
							devicesShaped.append(device['hostname'])
					print()
					minor += 1
			if 'children' in data[elem]:
				minor = traverseNetwork(data[elem]['children'], depth+1, major, minor+1, queue, elemClassID)
			#If top level node, increment to next queue
			if depth == 0:
				if queue >= queuesAvailable:
					queue = 1
					major = queue
				else:
					queue += 1
					major += 1
		return minor
	
	finalMinor = traverseNetwork(network, 0, major=1, minor=3, queue=1, parentClassID="1:1")
	
	#Recap
	for device in devices:
		if device['hostname'] not in devicesShaped:
			print('Device ' + device['hostname'] + ' was not shaped. Please check to ensure its parent Node is listed in network.json.')
	
	# Done
	currentTimeString = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
	print("Successful run completed on " + currentTimeString)

if __name__ == '__main__':
	refreshShapers()
	print("Program complete")
