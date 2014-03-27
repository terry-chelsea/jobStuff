#!/usr/bin/python
# coding:utf-8

import sys
import os
import time
import curses
import Queue
import signal
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler


serverIP = "0.0.0.0"
serverPort = 10240
g_requestQueue = Queue.Queue(maxsize = 10000)
logDirectory = "./log/"
gLogFiles = {}
errorLogFile = file(logDirectory + "error.log" , "w+")

#系统负载指标:最近一分钟负载值、最近五分钟、最近十五分钟
loadStatItemsName = {"one" : 6 , "five" : 6 , "fifteen" : 6}
#CPU指标:用户态使用率、内核态使用率、空闲率、IO等待时间比、上下文切换次数、当前运行进程数、阻塞进程数
cpuStatItemsName = {"user" : 6, "sys" : 6, "idel" : 6 , "iowait" : 6 , "ctxt" : 6 , "run" : 4 , "block" : 4}
#内存指标:系统总内存大小、当前空闲内存大小、cache所占内存大小、buffer大小、swap内存大小
memoryStatItemsName = {"total" : 8 , "free" : 8 , "cache" : 8 , "buffer" : 8 , "swap" : 8}
#磁盘指标:磁盘名（可能需要查看多个磁盘的信息）、读操作的完成数、写操作的完成数、读操作merge数、写操作merge数、当前尚未被执行的操作数、磁盘的使用率、读速度、写速度
diskStatItemsName = {"name" : 8 , "rIO" : 4 , "wIO" : 4 , "rMerge" : 6 , "wMerge" : 6, "wait" : 4 , "util" : 6, "rRate" : 8, "wRate" : 8}
#网卡指标:网卡名（可能查看多个）、接受到的包数、发送包数、读取速度、发送速度
netStatItemsName = {"name" : 8 , "rPackage" : 8, "wPackage" : 8, "rKB" : 8, "wKB" : 8} 
#socket指标:系统的socket总数、TCP连接数、UDP连接数、原始套接字数、IP段数、TIME_WAIT状态的TCP数
socketStatItemsName = {"socks" : 6 , "tcps" : 6 , "udps" : 6 , "raws" : 6, "IPFlag" : 6, "TWAIT" : 6}

globalStatItemsName = {}

dateHeadTitle = "DATE"
loadHeadTitle = "LOAD"
cpuHeadTitle = "CPU"
memoryHeadTitle = "MEMORY"
diskHeadTitle = "DISK"
netHeadTitle = "NET"
socketHeadTitle = "SOCKET"

itemLengthDict = {
					loadHeadTitle : loadStatItemsName , 
					cpuHeadTitle : cpuStatItemsName , 
					memoryHeadTitle : memoryStatItemsName , 
					diskHeadTitle : diskStatItemsName , 
					netHeadTitle : netStatItemsName , 
					socketHeadTitle : socketStatItemsName
				}

#IP地址与主机名之间的映射，由使用者配置`
#每个IP的主机名、需要显示磁盘名、网卡名和该IP的行号，前面三项由使用者配置，后面一项系统设置
#格式: IP:[name , [sda_names] , [netcards] , line]
IPToNameDict = {"127.0.0.1" : ["localHost" , ["sda"] , ["eth1"] , 0]}
linesPerHost = 2
maxHostNameLength = 0
hostNameStartPos = 2

#需要显示的指标名，依次是负载、CPU、内存、磁盘、网卡...由使用者配置
#注意：配置的指标名必须出现在上面的*StatItemsName中，否则将直接返回错误!
showItemsInfo = {
					loadHeadTitle : ["one" , "five" , "fifteen"] , 
					cpuHeadTitle : ["user" , "sys" , "idel"] , 
					memoryHeadTitle : ["total" , "free" , "buffer"] , 
					diskHeadTitle : ["name" , "rRate" , "wRate"] , 
					netHeadTitle : ["name" , "rPackage" , "wPackage" , "rKB" , "wKB"] , 
					socketHeadTitle : ["tcps" , "TWAIT"]
				}

g_screen = None

def combineAllStatNames() : 
	global globalStatItemsName
	global loadStatItemsName
	global cpuStatItemsName
	global memoryStatItemsName
	global diskStatItemsName
	global netStatItemsName
	global socketStatItemsName

	globalStatItemsName = dict(loadStatItemsName , **cpuStatItemsName)
	globalStatItemsName = dict(globalStatItemsName , **memoryStatItemsName)
	globalStatItemsName = dict(globalStatItemsName , **diskStatItemsName)
	globalStatItemsName = dict(globalStatItemsName , **netStatItemsName)
	globalStatItemsName = dict(globalStatItemsName , **socketStatItemsName)

def itemsWidth(name) :
	global itemLengthDict

	width = 0
	showItems = showItemsInfo.get(name)
	if not showItems : 
		return 0
	
	for item in showItems : 
		itemLength = itemLengthDict[name]
		length = itemLength.get(item)
		if not length : 
			print "Can not find lebal %s in items %s !" %(item , name)
			curses.endwin()
			sys.exit(-1)
		
		width += length + len(item) + 1

	return width

#计算显示一台机器信息需要的字节宽度，如果有一个机器需要显示的内容大于预定值，则需要重新配置
def calculateWidth() : 
	global IPToNameDict
	global showItemsInfo
	global linesPerHost
	global maxHostNameLength

	#固定的宽度，除了磁盘和网卡的宽度
	fixedWidth = 0
	loadWidth = itemsWidth(loadHeadTitle)
	cpuWidth = itemsWidth(cpuHeadTitle)
	memoryWidth = itemsWidth(memoryHeadTitle)
	diskWidth = itemsWidth(diskHeadTitle)
	netWidth = itemsWidth(netHeadTitle)
	socketWidth = itemsWidth(socketHeadTitle)	

	fixedWidth = loadWidth + cpuWidth + memoryWidth + socketWidth
	maxLength = 0
	currentLine = 2
	try : 
		for ip in IPToNameDict.keys() : 
			items = IPToNameDict[ip]
			addLength = len(ip)
			nameLength = len(items[0])

			if addLength < nameLength :
				addLength = nameLength

			#为每一行添加一个"|"作为分割线
			addLength += 1
			if addLength > maxHostNameLength : 
				maxHostNameLength = addLength
			#每一行都要显示这些信息
			addLength *= linesPerHost
			diskNum = len(items[1])
			netNum = len(items[2])
			
			addLength += diskNum * diskWidth + netNum * netWidth + 2

			if addLength > maxLength : 
				maxLength = addLength
			items[3] = currentLine
			currentLine += linesPerHost

	except BaseException , e : 
		print "some index maybe error : %s" %str(e)
		curses.endwin()
		sys.exit(-1)

	return addLength + fixedWidth , currentLine
	
def checkLengthAndWidth() : 
	global linesPerHost

	maxLines = curses.LINES - 2
	maxCols = curses.COLS - 4

	width , lines = calculateWidth()
	if lines > maxLines or width > maxCols * linesPerHost : 
		print "too big to display , max size : (%d , %d) , setting size : (%d , %d) ..." %(maxLines , maxCols * linesPerHost, width , lines)
		curses.endwin()
		sys.exit(0)
	
#	print "windows size : (%d , %d) , setting size : (%d , %d) ..." %(maxLines , maxCols * linesPerHost, lines , width)

def parseInfos(input) : 
	string = ""
	statDict = {}
	items = input.split("-")
	for item in items : 
		pair = item.split("_")
		if len(pair) != 2 : 
			errorLogFile.write("BUG : %s !!!\n" % item)
			errorLogFile.write("this is an error line : %s\n" %input)
		string += "%s(%s) " %(pair[0] , pair[1])
		statDict[pair[0]] = pair[1]
	
	return string[0 : -1] , statDict

#normalSequence = [dateHeadTitle, loadHeadTitle, cpuHeadTitle, memoryHeadTitle]

def addToDisplayValues(allValues , title , values) : 
	global showItemsInfo
	global globalStatItemsName

	needToDisplay = showItemsInfo.get(title)
	if not needToDisplay : 
		return 
	
	for item in needToDisplay : 
		value = values.get(item)
		if not value : 
			continue 
		allValues.append((item , value , globalStatItemsName[item]))

def writeLog(title , value , log)  :
	log.write("%s: %s" %(title , value))

def drawHostStats(hostName , ip , start , toDisplay) : 
	global g_screen
	global errorLogFile
	global maxHostNameLength
	global hostNameStartPos

	currentLength = maxHostNameLength + hostNameStartPos + 1
	currentLine = start
	maxLength = curses.COLS - 4

	for item in toDisplay : 
		key = item[0]
		value = item[1]
		length = item[2]

		infoString = "%s:%s%s " %(key , value , " " * (length - len(value)))
		nextLength = currentLength + len(infoString)
		if nextLength < maxLength : 
			errorLogFile.write("one : write line : %d , column : %d\n" %(currentLine , currentLength))
			g_screen.addstr(currentLine , currentLength , infoString)
			currentLength = nextLength
		else :
			currentLength = maxHostNameLength + hostNameStartPos + 1
			currentLine += 1
			errorLogFile.write("two : write line : %d , column : %d\n" %(currentLine , currentLength))
			g_screen.addstr(currentLine , currentLength , infoString)
			currentLength += len(infoString)
	
	g_screen.refresh()
	
def updateThisHost(params , ip , setting , log) : 
	global errorLogFile
	parseStats = {}
	showStats = []
	hostName = setting[0]
	settingDisks = setting[1]
	settingNets = setting[2]
	startLine = setting[3]
	
	allDisplayItemsValue = []
	line = "-" * 32
	log.write(line + "\n")
	for s in params : 
		info = s.split("=")
		if len(info) != 2 : 
			continue ;
			
		if info[0] == dateHeadTitle : 
			local = time.localtime(int(info[1]))
			timeString = time.strftime("%Y-%m-%d %H:%M:%S" , local)
#			parseStats[dateHeadTitle] = timeString
			writeLog(dateHeadTitle , timeString , log)

		elif info[0] == loadHeadTitle : 
			values = info[1].split("_")
			if len(values) != len(loadStatItemsName) : 
				errorLogFile.write(str(params) + "\n")
				errorLogFile.write("load stat infomations error !\n")

#			parseStats[loadHeadTitle] = [str(value) for value in values]
			loadDict = dict(zip(loadStatItemsName , [str(value) for value in values]))
			addToDisplayValues(allDisplayItemsValue , loadHeadTitle , loadDict)
			writeLog(loadHeadTitle , info[1].replace("_" , " ") , log)

		elif info[0] == cpuHeadTitle : 
			cpuString , cpuStat = parseInfos(info[1])
#			parseStats[cpuHeadTitle] = cpuString 
			addToDisplayValues(allDisplayItemsValue , cpuHeadTitle , cpuStat)
			writeLog(cpuHeadTitle , cpuString , log)

		elif info[0] == memoryHeadTitle :
			memoryString , memoryStat = parseInfos(info[1])
#			parseStats[memoryHeadTitle] = memoryString
			addToDisplayValues(allDisplayItemsValue , memoryHeadTitle , memoryStat)
			writeLog(memoryHeadTitle , memoryString , log)

		elif info[0] == diskHeadTitle : 
			disks = info[1].split("--")
			counter = 0
			for diskInfo in disks : 
				newTitle = diskHeadTitle + str(counter)
				diskString, diskStat = parseInfos(diskInfo)
#				parseStats[newTitle] = diskString
				counter += 1
				if diskStat['name'] in settingDisks : 
					addToDisplayValues(allDisplayItemsValue , diskHeadTitle , diskStat)
				writeLog(newTitle , diskString , log)
#			diskCount = counter


		elif info[0] == netHeadTitle : 
			nets = info[1].split("--")
			counter = 0
			for netInfo in nets : 
				newTitle = netHeadTitle + str(counter)
				netString , netStat = parseInfos(netInfo)
				#没有name，说明这是socket信息
				if not netStat.has_key('name') : 
					addToDisplayValues(allDisplayItemsValue , socketHeadTitle , netStat)
					writeLog(newTitle , netString , log)
					continue ;

#				parseStats[newTitle] = newString
				counter += 1
				if netStat['name'] in settingNets : 
					addToDisplayValues(allDisplayItemsValue , netHeadTitle , netStat)
				writeLog(newTitle , netString , log)
			netCount = counter
		
#	drawString(parseStats , diskCount , netCount , ip , logFile)
	drawHostStats(ip , hostName , startLine , allDisplayItemsValue)

class HTTPHandler(BaseHTTPRequestHandler) : 
	global gLogFiles
	global IPToNameDict

	def log_message(self, format, *args):
		return

	def do_GET(self) : 
		self.send_responce(200)
		self.end_headers()
		self.wfile.write("No GET supported !")
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
			logFile = file(logDirectory + ip + ".log" , "w+")
			gLogFiles[ip] = logFile
		
		data = self.rfile.read(length)
		responseStr = "OK"
		if ip not in IPToNameDict.keys() : 
			responseSt = "No IP infomation , setting first !"
		else :
			params = data.split("&")
			updateThisHost(params , ip , IPToNameDict[ip] , logFile)
		self.send_response(200)
		self.end_headers()
		self.wfile.write(responseStr)
		return 

def initShowHostNames() : 
	global g_screen
	global IPToNameDict

	for ip in IPToNameDict.keys() : 
		infos = IPToNameDict[ip]
		ipString = "%s%s|" %(ip , " " * (maxHostNameLength - 1 - len(ip))) 
		nameString = "%s%s|" %(infos[0] , " " * (maxHostNameLength - 1 - len(infos[0])))
		g_screen.addstr(infos[3] , hostNameStartPos , ipString)
		g_screen.addstr(infos[3] + 1 , hostNameStartPos , nameString)
	
	g_screen.refresh()

def sigHandle(sig=0, e=0) : 
	global gLogFiles

	curses.endwin()
	for fp in gLogFiles.values() : 
		fp.close()

	errorLogFile.close()
	os.system('clear')
	sys.exit(0)

def main() : 
	global g_screen

	signal.signal(signal.SIGINT, sigHandle)
	signal.signal(signal.SIGTERM, sigHandle)
	
	g_screen = curses.initscr()
	os.system('clear')
	g_screen.clear()
	g_screen.border(0)
	checkLengthAndWidth()	
	combineAllStatNames() 

	initShowHostNames()

	server = HTTPServer((serverIP , serverPort) , HTTPHandler)
	server.serve_forever()


if __name__ == "__main__" : 
	main()
