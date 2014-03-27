#!/usr/bin/python
#coding:UTF-8

'''
显示服务器:
接收到客户端的POST请求，对于其他请求恢复404错误，POST的内容部分为需要显示的数据
每次显示从当前位置开始，如果显示超出一页，自动从上向下刷新
双线程工作：主线程用于接收请求，通过Queue交给子线程显示
'''

import sys
import os
import curses
import Queue
import time
import signal
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

dateHeadTitle = "DATE"
loadHeadTitle = "LOAD"
cpuHeadTitle = "CPU"
memoryHeadTitle = "MEMORY"
diskHeadTitle = "DISK"
netHeadTitle = "NET"

serverIP = "0.0.0.0"
serverPort = 10240
g_requestQueue = Queue.Queue(maxsize = 10000)
g_screen = curses.initscr()

gLogFiles = {}
	
def 
	string = ""
	items = input.split("-")
	for item in items : 
		pair = item.split("_")
		if len(pair) != 2 : 
			print "BUG : %s !!!" % item
			return "this is an error line : " + input
		string += "%s(%s) " %(pair[0] , pair[1])
	
	return string[0 : -1]

normalSequence = [dateHeadTitle, loadHeadTitle, cpuHeadTitle, memoryHeadTitle]
maxLines = curses.LINES - 4;
maxCols = curses.COLS - 16
startPos = [1 , 6]
spaceLine = " " * maxCols

def drawLine(line , log) : 
	g_screen.addstr(startPos[0], startPos[1], spaceLine)
	g_screen.addstr(startPos[0], startPos[1], line)	
	startPos[0] += 1
	
	log.write(line + "\n")


def drawString(parseStats , disks , nets , ip , logFile) : 
	global normalSequence
	global maxLines
	global maxCols
	global startPos
	global spaceLine

	lines = len(normalSequence) + disks + nets + 1
	
	if startPos[0] + lines >= maxLines : 
		startPos[0] = 1;

	infoLine = "-" * ((maxCols - len(ip)) / 2)
	drawLine("%s%s%s" % (infoLine , ip , infoLine) , logFile)	

	for title in normalSequence : 
		drawLine("%s: %s" % (title, parseStats[title]) , logFile)	
	
	for i in range(0 , disks) : 
		key = diskHeadTitle + str(i)
		drawLine("%s: %s" %(key , parseStats[key]) , logFile)

	for i in range(0 , nets) : 
		key = netHeadTitle + str(i)
		drawLine("%s: %s" %(key , parseStats[key]) , logFile)

	g_screen.refresh()

def displayStat(stat , ip , logFile) : 
	global g_screen

	parseStats = {}
	diskCount = 0;
	netCount = 0
	for s in stat : 
		info = s.split("=")
		if len(info) != 2 : 
			continue ;
			
		if info[0] == dateHeadTitle : 
			local = time.localtime(int(info[1]))
			timeString = time.strftime("%Y-%m-%d %H:%M:%S" , local)
			parseStats[dateHeadTitle] = timeString

		elif info[0] == loadHeadTitle : 
			values = info[1].split("_")
			parseStats[loadHeadTitle] = [str(value) for value in values]

		elif info[0] == cpuHeadTitle : 
			parseStats[cpuHeadTitle] = toString(info[1])

		elif info[0] == memoryHeadTitle :
			parseStats[memoryHeadTitle] = toString(info[1])

		elif info[0] == diskHeadTitle : 
			disks = info[1].split("--")
			counter = 0
			for info in disks : 
				parseStats[diskHeadTitle + str(counter)] = toString(info)
				counter += 1
			diskCount = counter

		elif info[0] == netHeadTitle : 
			nets = info[1].split("--")
			counter = 0
			for info in nets : 
				parseStats[netHeadTitle + str(counter)] = toString(info)
				counter += 1
			netCount = counter
		
	drawString(parseStats , diskCount , netCount , ip , logFile)

class HTTPHandler(BaseHTTPRequestHandler) : 
	global gLogFile

	def log_message(self, format, *args) : 
		return 

	def do_GET(self) : 
		self.send_responce(200)
		self.end_headers()
		self.wfile.write("OK")
		return 
	
	def do_POST(self) : 
		length = 0
		for para , value in self.headers.items() : 
			if para == "content-length" : 
				length = int(value.strip())
				break

		ip = self.client_address[0];
		logFile = gLogFiles.get(ip)
		if not logFile : 
			logFile = file(ip + ".log" , "w+")
			gLogFiles[ip] = logFile

		addr = ip + ":" + str(self.client_address[1])

		data = self.rfile.read(length)
		params = data.split("&")
		displayStat(params , addr , logFile)
		self.send_response(200)
		self.end_headers()
		self.wfile.write("OK")
		return 

def sigHandle(sig=0, e=0) : 
	global gLogFiles

	curses.endwin()
	for fp in gLogFiles.values() : 
		fp.close()

	sys.exit(0)

def main() : 
	global g_screen

	signal.signal(signal.SIGINT, sigHandle)
	signal.signal(signal.SIGTERM, sigHandle)
	
	os.system('clear')
	g_screen.clear()
	g_screen.border(0)
	
	server = HTTPServer((serverIP , serverPort) , HTTPHandler)
	server.serve_forever()


if __name__ == "__main__" : 
	main()
