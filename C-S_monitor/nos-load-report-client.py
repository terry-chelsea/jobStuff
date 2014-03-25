#!/usr/bin/python
# -*- coding:UTF-8

'''
汇报当前主机的时间/负载状况/CPU/内存/磁盘和网络的运行状态。
通过HTTP报文的格式汇报给服务器，全部信息通过它HTTP报文的URL的参数传递
参数格式如下:

http://hostIP:port?IP=客户端IP?DATE=汇报时间?LOAD=系统负载?

CPU=user:用户态-sys:内核态-idel:空闲-wa:IO等待-cs:上下文切换-running:正在运行进程数-block:阻塞进程数
MEMORY=total:总大小-free:空闲大小-cache:磁盘缓存-buffer:设备缓冲-swap:换页

DISK=name:设备名-rIO:读操作完成数-wIO:写操作完成数-rMer:读操作合并数-wMer:写操作合并数-rSec:读扇区数-wSec:写扇区数-wait:尚未执行-IOUtil:利用率-rRt:读速率-wRt:写速率

NET=name:网卡名-rPk:读取包速率-wPk:发送包速率-rKb:接受速率-wKb:发送速率-allSock:全部套接字数-tcpSock:TCP套接字数-udpSock:TCP套接字数-rawSock:原始套接字数-tcpTW:处于TIME_WAIT状态TCP套接字数
'''

import os
import time
import sys
import signal
import getopt
import httplib
import urllib

dateHeadTitle = "DATE"
loadHeadTitle = "LOAD"
cpuHeadTitle = "CPU"
memoryHeadTitle = "MEMORY"
diskHeadTitle = "DISK"
netHeadTitle = "NET"
socketHeadTitle = "SOCKET"

cpuStatItemsName = ["user" , "sys" , "idel" , "iowait" , "ctxt" , "running" , "blocked"]
memoryStatItemsName = ["total" , "free" , "cache" , "buffer" , "swap"]
diskStatItemsName = ["name" , "rIO" , "wIO" , "rMerge" , "wMerge" , "wait" , "util" , "rRate" , "wRate"]
netStatItemsName = ["name" , "rPackage" , "wPackage" , "rKB" , "wKB"] 
socketStatItemsName = ["sockets" , "tcps" , "udps" , "raws" , "IPFlag" , "TWAIT"]

g_logFile = None

diskBase = {}
cpuBase = []
serverIP = "127.0.0.1"
serverPort = 10240
g_stopFlag = False

def getCurrentDate() : 
	current = time.time()
	return str(int(current))

def getFileContents(name) : 
	try : 
		fp = file(name)
		lines = fp.readlines()
		fp.close()
	except BaseException , e : 
		print "read from file %s failed : %s" %(name , str(e))
		return None

	return lines;

def getSystemLoad() : 
	loadFileName = "/proc/loadavg"
	loads = getFileContents(loadFileName)
	if not loads :
		return None
	line = loads[0]

	cells = line.strip().split()
	cells = cells[0 : 3]
	loadString = cells[0] + "_"
	loadString += cells[1] + "_"
	loadString += cells[2]
	return loadString;

def firstCpuStatistics() : 
	cpuFileName = "/proc/stat"
	lines = getFileContents(cpuFileName)
	if not lines :
		return None

	cpuBase = []
	cpuInfos = lines[0].strip().split()
	#只考虑CPU后面的统计数字部分
	for i in range(1 , len(cpuInfos)) : 
		cpuBase.append(int(cpuInfos[i]))
	
	#上下文切换统计数
	ctxtInfo = lines[3].strip().split()
	cpuBase.append(int(ctxtInfo[1]))
	print cpuBase
	return cpuBase
	

def toString(items) : 
	strItems = []
	for value in items : 
		strItems.append(str(value))

	return strItems

def getCpuState() : 
	global cpuBase
	base = cpuBase

	statFileName = "/proc/stat"
	lines = getFileContents(statFileName)
	if not lines :
		return None

	cpuInfos = lines[0].strip().split()
	gapInfos = []
	sumTime = 0
		
	for i in range(0 , len(cpuInfos) - 1) : 
		#每次统计的当前计数值
		curValue = int(cpuInfos[i + 1])
		gapInfos.append(curValue - base[i])
		base[i] = curValue
		sumTime += gapInfos[-1]
	#用户态时间
	userTime = round(float(gapInfos[0]) / sumTime , 2)
	#内核态时间
	systemTime = round(float(gapInfos[2]) / sumTime , 2)
	#空闲时间
	idelTime = round(float(gapInfos[3]) / sumTime , 2)
	#IO等待时间
	ioWaitTime = round(float(gapInfos[4]) / sumTime , 2)
	
	#上下切换计数
	thisCtxt = int(lines[3].strip().split()[1])
	ctxtCounter = thisCtxt - base[-1]
	base[-1] = thisCtxt
	
	running = int(lines[6].strip().split()[1])
	blocked = int(lines[7].strip().split()[1])
	cpuStats = [userTime , systemTime , idelTime , ioWaitTime , ctxtCounter , running , blocked]
	#以字符串的形式返回
	return toString(cpuStats)	

def getMemoryState() : 
	memoryFileName = "/proc/meminfo"
	lines = getFileContents(memoryFileName)
	if not lines :
		return None

	memInfos = [cell.strip().split()[1] for cell in lines[0 : 5]]
	return memInfos

def getCurrentDiskStatistics(name) : 
	diskFileName = "/sys/block/%s/stat" % name
	lines = getFileContents(diskFileName)
	if not lines : 
		return None
	
	line = lines[0].strip()
	cells = line.split()
	cells = [int(i) for i in cells]
		
	return cells

def firstDiskStatistics(name) : 
	global diskBase
	stats = getCurrentDiskStatistics(name)
	if not stats : 
		print "Get disk statistics failed !"
		return None
	diskBase[name] = stats

def getDiskState(name , interval) : 
	global diskBase
	stat = getCurrentDiskStatistics(name)
	if not stat : 
		print "Get disk statistics failed !"
		return None

	if not diskBase.has_key(name) : 
		print "Disk %s name not exist ..."
		return None
	baseStat = diskBase[name]
	for i in range(0 , len(baseStat)) :
		baseStat[i] = stat[i] - baseStat[i]
		if baseStat[i] < 0 : 
			baseStat[i] = 0;
	
	diskBase[name] = stat

	#统计读写速率，统计数是扇区
	readRate = round(baseStat[2] * 0.5 / interval , 2)
	writeRate = round(baseStat[6] * 0.5 / interval , 2)
	utilize = round(baseStat[9] / (interval * 1000))
	diskStats = [baseStat[0] , baseStat[4] , baseStat[1] , baseStat[5] , stat[8] , utilize , readRate , writeRate]
	#以字符串的形式返回
	return toString(diskStats)

def getNetState(sec , names) : 
	commandLine = "sar -n DEV,SOCK %d 1" %sec
	try : 
		out = os.popen(commandLine)
		lines = out.readlines()
	
	except BaseException , e :
		print "Execute command %s failed : %s" %(commandLine , str(e))
		return None , None

	socketStat = lines[-1].strip().split()[1 : 7]
	
	cardLines = lines[3 : -2]
	flag = {}
	netInfos = {}
	#查找每一个网卡的信息
	for line in cardLines :
		cells = line.strip().split()
		#遍历到空行表示结束
		if not cells : 
			break;
		cardName = cells[1]
		if (not flag.has_key(cardName)) and (cardName in names) : 
			netInfos[cardName] = cells[2 : 6]
			flag[cardName] = True
	
	return netInfos , socketStat

def getStatString(name , stat) : 
	if(len(name) != len(stat)) : 
		print "error : %d and %d" %(len(name) , len(stat))
		print name , stat
		return None

	string = ""
	length = len(name)
	for i in range(0 , length) : 
		string += name[i] + "_" + stat[i] + "-"

	return string[0 : -1]

def getLoadStatistics(interval , diskNames , netNames) : 
	statDict = {}
	netStats , socketStat = getNetState(interval , netNames)
	if not netStats : 
		print "Get net statistics failed !"
		return None
	
	#添加时间信息
	statDict[dateHeadTitle] = getCurrentDate()
	line = getSystemLoad()
	if not line : 
		print "Get system load statistics failed !"
		return None
	#添加最近系统负载
	statDict[loadHeadTitle] = line

	#添加CPU信息
	cpuStat = getCpuState()
	if not cpuStat : 
		print "Get CPU statistics failed !"
		return None
	statDict[cpuHeadTitle] = getStatString(cpuStatItemsName , cpuStat)
	
	#添加内存信息
	memoryStat = getMemoryState()
	if not memoryStat : 
		print "Get memory statistics failed !"
		return None 
	statDict[memoryHeadTitle] = getStatString(memoryStatItemsName , memoryStat)

	#添加磁盘信息
	diskString = ""
	for disk in diskNames : 
		diskStat = getDiskState(disk , interval)
		if not diskStat : 
			print "Get disk %s statistics failed " % disk
			return None
		diskValue = [disk]
		diskValue.extend(diskStat)
		diskString += getStatString(diskStatItemsName , diskValue) + "--"
	statDict[diskHeadTitle] = diskString[0 : -2]
	
	netString = ""
	for name in netNames : 	
		if netStats.has_key(name) :
			netValue = [name]
			netValue.extend(netStats[name])
			netString += getStatString(netStatItemsName , netValue) + "--"

	netString += getStatString(socketStatItemsName , socketStat)
	statDict[netHeadTitle] = netString

	return statDict

def intHandler(sig=0 , e=0) : 
	global g_logFile
	global g_stopFlag
	
	if g_logFile : 
		g_logFile.close()
	g_stopFlag = True

def Usage() : 
	print "nos-load-report-client.py  version 1.01"
	print "./nos-load-report-client.py [选项]"
	print "Options are : "
	print "-d {<disk_name> [,...]}"
	print "-n {<net_card> [,...]}"
	print "[-v]"

def sendToServer(load) :
	try : 
		conn = httplib.HTTPConnection(serverIP , port = serverPort , timeout=10)
		params = urllib.urlencode(load)
		headers = {}
		conn.request("POST" , "/" ,params , headers)
		ret = conn.getresponse()
		print ret.reason
	except BaseException , e : 
		print "Send URL to server %s:%d failed : %s " %(serverIP , serverPort , str(e))
		return False
	
	return True

def main() : 
	global http_url_header
	global cpuBase
	global g_logFile
	global g_stopFlag
	
	disks = []
	nets = []
	opts , args = getopt.getopt(sys.argv[1:] , "d:n:f:v" , []);
	for opt in opts : 
		if opt[0] == "-d" : 
			disks = opt[1].strip().split(",")
			disks = [name.strip() for name in disks]
		elif opt[0] == "-n" : 
			nets = opt[1].strip().split(",")
			nets = [name.strip() for name in nets]
		elif opt[0] == "-v" : 
			Usage()
			sys.exit(0)
		elif opt[0] == "-f" : 
			g_logFile = file(opt[1] , "a")

	if not disks or not nets : 
		print "Must set at least one disk name and one Network card name !"
		Usage()
		sys.exit(-1)

	signal.signal(signal.SIGINT , intHandler)
	cpuBase = firstCpuStatistics()
	for name in disks : 
		firstDiskStatistics(name)

	while(not g_stopFlag) : 
		start = time.time()
		loadString = getLoadStatistics(1 , disks , nets)
		if not loadString : 
			print "Get system statistics failed !"
			return None
		end = time.time()

		print("-----------------------------------")
		print "Cost time : %f" % (end - start)
		print loadString
		if not sendToServer(loadString) : 
			print "Send to server failed !"
			return None 
		print("-----------------------------------")

if __name__ == "__main__" : 
	main()
