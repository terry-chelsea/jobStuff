#!/usr/bin/python
# coding:utf-8

'''
create at 2014-4-3
author:fengyuatad@126.com
'''

import time
import signal
import os
import sys
import curses
import Queue
import threading
import urlparse
from BaseHTTPServer import HTTPServer , BaseHTTPRequestHandler

#日志信息，记录所有客户端发送的数据
g_logFileNamePrefix = "moniter_log_"
g_logFileHandler = None
#客户端Host与缩写之间的映射，由客户端注册时候设置，如果存在重复的注册或者缩写，给予拒绝的回复
#HostName : shortName
g_machineTable = {}

g_localIP = "0.0.0.0"
g_localPort = 16161
#每一项的信息，包括显示的名称，每一项所占的长度，显示的位置，以及对应的阀值
#shortName.itemName : [line , col , length , limit_type , limits]
g_itemLocationTable = {}
#当前排列的一列中需要占据最大长度项的长度
g_currentMaxItemLength = 0
#下一次的排列的行数和列数
g_currentLine = 1
g_currentColumn = 1
g_direction = 0
g_noSpaceFlag = False

#在需要的时候在创建curses
g_screen = None

#主线程与子线程通信队列,消息格式是一个dict，包含cmd字段表示命令的类型
g_requestQueue = Queue.Queue(maxsize = 10000)

g_showThread = None
#主线程向显示线程发送的命令类型
g_commandName = 'cmd'
cmdStartThread = 0
cmdClientInfo = 2
cmdEndThread = 3

def sigHandler(sig = 0 , e = 0) : 
	global g_showThread
	global g_logFileHandler

	#通过向显示线程发送结束请求来结束线程
	stop_thread()

	#等待1秒,如果显示线程仍没有退出，直接exit
	retryTime = 10
	for i in range(0 , retryTime) : 
		if g_showThread.isAlive() : 
			time.sleep(0.1)
		else : 
			break;

	g_logFileHandler.close()
	curses.endwin()
	os.system('clear')
	os._exit(0)

def sendRequestToThread(req) :
	global g_requestQueue
	
	try : 
		g_requestQueue.put(req , block = False)
	except BaseException , e : 
		print "Nonblocking Write to show thread failed , reason : %s" %str(e)
		return 

def start_thread() : 
	global cmdStartThread

	startMessage = "Simple Monitor Server Display Board"
	startDict = {}
	startDict[g_commandName] = cmdStartThread
	startDict['message'] = startMessage
	startDict['line'] = 1
	startDict['col'] = (curses.COLS - len(startMessage)) / 2
	sendRequestToThread(startDict)
	return 

def stop_thread() : 
	global cmdEndThread

	endDict = {}
	endDict[g_commandName] = cmdEndThread
	sendRequestToThread(endDict)
	return 

def logInfos(info) : 
	global g_logFileHandler

	current = time.strftime("%H:%M:%S" , time.localtime())
	info = current + " " + info + "\n"
	g_logFileHandler.write(info)

def displayOnBoard(line , col , msg , color) : 
	global g_screen
	
	if color : 
		g_screen.addstr(line , col , msg , color)
	else : 
		g_screen.addstr(line , col , msg)

def displayError(msg) : 
	global g_screen

	displayOnBoard(curses.LINES - 1 , 1 , msg , curses.color_pair(1))
	g_screen.refresh()

def clientRegister(req) : 
	global g_currentMaxItemLength
	global g_currentLine
	global g_currentColumn
	global g_direction
	global g_itemLocationTable

	noSpaceFlag = False
	#弹出，获得这两项的值
	hostname = req.pop('hostname')
	shortname = req.pop('_shortname_')
	logLine = "Register infomation , hostName : %s , shortName : %s" %(hostname , shortname)
	errorLinePrefix = "Error register infomation , hostName : %s , shortName : %s" %(hostname , shortname)
	errorLine = ""
	ack = 200
	localPosDict = {}

	for item in req.keys() : 
		#真正显示的名称
		itemName = shortname + "." + item
		itemLen = len(itemName) + len(":")
		value = req[item]
		#注册报文中的长度和阀值通过"_"分割
		cells = value.strip().split('_')
		if len(cells) != 2 : 
			msg = " ; item %s value %s error" %(itemName , value)
			errorLine += msg
			continue;
		if noSpaceFlag :
			errorLine += " ; No space for %s value %s" %(itemName , value)
			continue 
		#显示需要的长度
		length = cells[0]
		limit_type = cells[1][0]
		limit = ""
		#根据客户端的设置确定显示颜色的情况，默认是大于的时候显示
		limitsTypeTable = {'b' : 1 , 'e' : 0 , 's' : -1}
		if limit_type in limitsTypeTable.keys() : 
			limit_type = limitsTypeTable[limit_type]
			limit = cells[1][1 : ]
		else : 
			limit_type = 1
			limit = cells[1]
		#转换这两个数值，并且判断是否可以转换成对应的类型
		try : 
			length = int(cells[0])
			limit = float(limit)
		except BaseException , e : 
			msg = " ; item %s value %s error : value error" %(itemName , value)
			errorLine += msg
			continue;
		
		#计算显示该项所需要的宽度
		itemLen += length
		if itemLen > g_currentMaxItemLength : 
			g_currentMaxItemLength = itemLen
			if g_currentColumn + g_currentMaxItemLength > curses.COLS : 
				g_noSpaceFlag = True
				break;

		#根据当前的方向设置下一行显示的位置
		if g_direction : 
			g_currentLine -= 1
			if g_currentLine == 1 : 
				g_currentLine += 1
				g_currentColumn += g_currentMaxItemLength
				g_currentMaxItemLength = 0
				g_direction = not g_direction
		else :
			g_currentLine += 1 
			if g_currentLine == curses.LINES - 1 :
				g_currentLine -= 1
				g_currentColumn += g_currentMaxItemLength
				g_currentMaxItemLength = 0
				g_direction = not g_direction

			
		localPosDict[itemName] = [g_currentLine , g_currentColumn , length , limit_type , limit] 
		logLine += " ; [name : %s , line : %d , column : %d , length : %d , limit_type : %d , limit : %f"  \
			%(itemName , g_currentLine , g_currentColumn , length , limit_type , limit)	

	logInfos(logLine)
	if errorLine == "": 
		for item in localPosDict : 
			g_itemLocationTable[item] = localPosDict[item]

		return 200 , "OK"
	else : 
		logInfos(errorLinePrefix + errorLine)
		return 400 , errorLinePrefix + errorLine
	
def getClientInfomation(req) : 
	global g_itemLocationTable
	global g_screen

	hostname = req.pop('hostname')
	shortname = req.pop('_shortname_')
	logLine = "Display infomation , hostName : %s , shortName : %s" %(hostname , shortname)
	errorLinePrefix = "Error display infomation , hostName : %s , shortName : %s" %(hostname , shortname)
	errorLine = errorLinePrefix

	for item in req.keys() :
		itemName = shortname + "." + item
		displayValue = req[itemName].strip()
		values = g_itemLocationTable.get(itemName)
		color = None
		if itemName == None : 
			msg = " ; %s has not register for host %s" %(itemName , hostname)
			displayError(msg)
			errorLine += msg
			continue 
		length = values[2]
		floatValue = 0
	
		#尝试把值转换成float类型，如果失败则记录错误
		try : 
			floatValue = float(displayValue)
		except BaseException , e : 
			msg = " ; %s has no invalid value %s from host %s" %(itemName , displayValue , hostname)
			displayError(msg)
			errorLine += msg
			continue 
		
		limitType = values[3]

		#根据设置的阀值设置显示颜色
		if (limitType == 1 and floatValue > values[4]) or  \
			(limitType == 0 and floatValue == values[4]) or \
			(limitType == -1 and floatValue < values[4]) : 
			color = curses.color_pair(1)

		displayValue = convertNumberwithUnit(floatValue)

		#超出长度则显示 ***
		if len(displayValue) > length : 
			displayValue = "*" * length
			color = curses.color_pair(1)

		#不存存在覆盖的情况，因为itemName的长度不变，value总是被填充
		displayValue  = displayValue.ljust(length)
		logLine += " , %s : %s" %(itemName , displayValue)
		
		displayOnBoard(values[0] , values[1] , "%s%s%s"%(itemName , ":" , displayName) , color)
	
	g_screen.refresh()
	logInfos(logLine)
	if not errorLine == errorLinePrefix: 
		logInfos(errorLine)

def convertNumberwithUnit(value) : 
	if value >= 1000000 : 
		value = round(value / 1000000.0 , 1)
		return "%.1fM" %value
	elif value >= 1000 : 
		value = round(value / 1000.0 , 1)
		return "%.1fK" %value
	else : 
		value = round(value , 1)
		return "%.1fs" % value

def dealWithRequest(req) : 
	global cmdStartThread
	global cmdEndThread
	global cmdClientInfo
	global g_commandName
	global g_screen
	
	cmd = req[g_commandName]
	if cmd == cmdStartThread : 
		displayOnBoard(req['line'] , req['col'] , req['message'] , curses.color_pair(2))
		g_screen.refresh()
		msg = "Init message : %s" %req['message']
		logInfos(msg)
	elif cmd == cmdEndThread :
		msg = "Stop thread ..."
		logInfos(msg)
		return 1
	elif cmd == cmdClientInfo : 
		getClientInfomation(req)
	else : 
		logInfos("undefined command : %d" %cmd)

	return 0

class showThread(threading.Thread) : 
	def __init__(self) : 
		threading.Thread.__init__(self)
		self.name = "showThread"

	def run(self) : 
		global g_requestQueue
		#读取操作是阻塞式的，所以不需要其他的方式同步
		while True : 
			req = g_requestQueue.get()
			ret = dealWithRequest(req)
			#当收到接受请求的时候跳出循环
			if ret : 
				break

#处理HTTP请求的回调函数，在收到GET或者POST请求的时候回调
class HttpReqHandler(BaseHTTPRequestHandler) : 
	def log_message(self , format , *args) :
		return 

	def go_GET(self) : 
#		self._dealWithHttpRequest()
		self.send_response(200 , '200 OK')
		return 

	#对于POST请求直接回复"未实现"
	def do_POST(self) : 
		self.send_response(501 , '501 Not implemented')
		return 
	
	def sendResponse(self , ack , reason) : 
		self.send_request(ack)
		self.end_headers()
		self.wfile.write(reason)
		return 

	def _dealWithHttpRequest(self) : 
		global g_machineTable
		global g_commandName
		global cmdClientInfo
		global g_noSpaceFlag

		#解析URL中出现的所有参数信息，所有的信息都是通过URL传送
		resource = urlparse.urlparse(self.path).path
		argumentList = urlparse.parse_qs(urlparse.urlparse(self.path).query , True)
		print str(argumentList)
		
		#请求的资源必须为"/"，否则不予处理
		if resource != '/' and resource != "" : 
			self.sendResponse(400 , '400 Not Found')
			return 
	
		#将URL中所有的参数转换成字典
		parameters = dict([(k , v[0] if len(v) > 0 else "") for k , v in argumentList.items()])
		cmd = parameters.get('_command_')
		#查看是否存在command段，每一个请求都应该存在！
		if None == cmd : 
			self.sendResponse(400 , '400 request error : request should has a command type !')
			return 
	
		#每一个请求都应该携带hostname项
		#对于注册请求需要满足几个条件:当前仍可以注册，有剩余空间；hostname不能为空；尚未注册；拥有缩写并且缩写没有被占用
		hostName = parameters.get('hostname')
		if cmd == '_register_' : 
			if None == hostName : 
				self.sendResponse(400 , '400 request error : register request need has hostname !')
				return 
			#不能重复注册...注册信息必须携带主机名的缩写信息
			elif g_machineTable.has_key(hostName) :
				self.sendResponse(409 , '409 Confict : Only Allow to register once for each client or another node has the same hostname!')
				return 
			elif not parameters.has_key('_shortname_')  : 
				self.sendResponse(400 , '400 request error : register request must has shortname !')
				return 
			elif parameters['_shortname_'] in g_machineTable.values() : 
				self.sendResponse(409 , '409 Conflict : another host has the same shortName , rename it !')
				return 
			#如果格式正确，标记该主机已注册，向显示线程发送注册请求
			else : 
				parameters.pop('_command_')

				#直接在主线程执行注册，注册只会添加不会修改，所以不需要加锁...
				ack , ackInfo = clientRegister(parameters)
				self.sendResponse(ack , ackInfo)

		#对于消息请求，需要携带主机名以判断是否已经注册，向显示线程发送显示请求
		elif cmd == '_info_' : 
			if None == hostName : 
				self.sendResponse(400 , '400 request error : infomation request need has hostname !')
				return 
			elif g_machineTable.has_key(hostName) :
				self.sendResponse(409 , '409 Confict : Should register before send infomations !')
				return 
			else : 
				parameters.pop('_command_')
				parameters[g_commandName] = cmdClientInfo
				parameters['_shortname_'] = g_machineTable[hostName]

				sendRequestToThread(parameters)
				self.sendResponse(200 , "200 , OK : infomation success ...")

		#对于不识别的命令，回复错误
		else : 
			self.sendResponse(400 , '400 request error : undefined command type !')
			return 

def main() : 
	global g_screen
	global g_showThread
	global g_localIP
	global g_localPort
	global g_logFileNamePrefix
	global g_logFileHandler
	
	#注册信号，否则Ctrl+C会因为curses而使得屏幕乱码
	signal.signal(signal.SIGINT , sigHandler)
	signal.signal(signal.SIGTERM , sigHandler)
	#日志文件，以日期作为后缀，所有的客户端信息和错误都记录日志
	g_logFileNamePrefix += time.strftime("%Y-%m-%d" , time.localtime())
	g_logFileHandler = file(g_logFileNamePrefix , "w+")	

	#创建显示信息的线程,所有的显示和位置分布的操作都由它完成，主线程只负责与客户端的通信
	g_showThread = showThread()
	g_showThread.start()
	
	#初始化curses，设置颜色
	g_screen = curses.initscr()
	curses.start_color()
	curses.init_pair(1 , curses.COLOR_RED , curses.COLOR_BLACK)
	curses.init_pair(2 , curses.COLOR_YELLOW , curses.COLOR_BLACK)
	os.system("clear")
	g_screen.clear()
	g_screen.border(0)
	
	#向显示线程发送启动命令
	start_thread()
	server = HTTPServer((g_localIP , g_localPort) , HttpReqHandler)
	server.serve_forever()

	os._exit(0)

if __name__ == "__main__" : 
	main()
