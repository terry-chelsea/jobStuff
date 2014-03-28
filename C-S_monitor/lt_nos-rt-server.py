#!/usr/bin/env python
# -*- coding:UTF-8

'''
Created on 2014-03-27

@author: tangcheng
'''

from optparse import OptionParser
import time
import signal
import os
import logging
import sys
import urlparse
import threading
import traceback
import Queue
import curses
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler

g_logFile = file("temp_log" , "w")
g_serverIpAddr = '0.0.0.0'
g_port = 5737
g_delimiter = " : "
#机器名与显示短名称的映射字典，短名称用于显示，防止占用太多的屏幕空间
g_machineDict = {
    'noscoder1.server.163.org' : 'nc1',
    'noscoder2.server.163.org' : 'nc2',
    'noscoder3.server.163.org' : 'nc3',
    'noscoder4.server.163.org' : 'nc4',
    'noscoder5.server.163.org' : 'nc5',
    'noscoder6.server.163.org' : 'nc6',
    'noscoder7.server.163.org' : 'nc7',
    'noscoder8.server.163.org' : 'nc8',
    'noscoder9.server.163.org' : 'nc9',
    'noscoder10.server.163.org' : 'nc10',
    }

#显示指标值的字典, key为"机器短名称,指标名"，value为[x, y, title的长度，value的长度]
g_keyPosDict = {}

g_requestQueue = Queue.Queue(maxsize = 10000)
g_screen = None

g_statNames = ['cpuUtils' , 'diskUtils' , 'diskReadRate' , 'diskWriteRate' , 
				'netRecvBytes' , 'netSendBytes' , 'netRecvPacks' , 'netSendPacks']

def deployShowFrame() : 
    global g_keyPosDict
    global g_statNames
    global g_machineDict
    global g_delimiter

    fullNameLength = maxWidth()
    statValueLength = 6
   	
    gap = fullNameLength + statValueLength + len(g_delimiter) + 1
    currentLine = 1
    currentPos = 1
    for host in g_machineDict.values() : 
	    for name in g_statNames : 
		    fullName = "%s.%s" %(host , name)
		    g_keyPosDict[fullName] = [currentLine , currentPos , fullNameLength , statValueLength]
		    g_logFile.write("%s : %s\n" %(fullName , str([currentLine , currentPos , fullNameLength , statValueLength])))
		    currentLine += 1
		    if currentLine > curses.LINES - 1 : 
			    print "beyond the max line exit ..."
			    os.exit(-1)
	    
	    currentPos += gap
	    if currentPos + gap > curses.COLS - 2 : 
		    currentPos = 1
	    else : 
		    currentLine -= len(g_statNames)
    
def maxWidth() : 
    maxHostName = 0
    for host in g_machineDict.values() : 
        if len(host) > maxHostName : 
		    maxHostName = len(host)

    maxStatName = 0
    for name in g_statNames : 
	    if len(name) > maxStatName : 
		    maxStatName = len(name)
	
	#还需要一个分隔符
    return maxStatName + maxHostName + 1

def convertNumberwithUnit(value):
    value  = float(value)
    if value >=1000000:
        value = round(value /1000000.0, 1)
        return "%sM" % value 
    elif value >=1000:
        value = round(value /1000.0, 1)
        return "%sK" % value
    else :
        return "%s" % round(value, 1)

def showStats(statDict):
    global g_screen
    global g_keyPosDict
    global g_delimiter

    g_logFile.write(str(statDict) + "\n")
    #g_screen.addstr(19, 1, repr(statDict))
    try:
        hostname = statDict['hostname']

        shortHostname = g_machineDict[hostname]
        
        for key in statDict:
            posKey = "%s.%s" % (shortHostname, key)
            if posKey in g_keyPosDict:
                value = statDict[key]
                pos = g_keyPosDict[posKey]
                #补空格
                showKeyText = posKey[:pos[2]].rjust(pos[2])

                unitValue = convertNumberwithUnit(value)

                #g_screen.addstr(18, 1, str(len(unitValue)))
                
                #超过长度限制，则显示为“****”
                if len(unitValue) > pos[3]:
                    unitValue = '*'*pos[3]
                showValueText  = unitValue.ljust(pos[3])
                g_screen.addstr(pos[0], pos[1], "%s%s%s" % (showKeyText, g_delimiter , showValueText))
                
    except Exception, e:
        g_screen.addstr(curses.LINES - 1, 1, repr(e))
    g_screen.refresh()


class HttpHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        return

    def do_GET(self):
        self.__dealWithRequest()
        return

    def do_POST(self):
        self.__dealWithRequest()
        return
    
    def __dealWithRequest(self):
        Logger = logging.getLogger()
        #　获取的参数是一个字典，并且value是一个数组,形如{'q': ['abc'], 'p': ['123'], 'xx': ['']}
        #　参数True会解析出没有value的key
        argumentList = urlparse.parse_qs(urlparse.urlparse(self.path).query, True)

        g_logFile.write(str(argumentList) + "\n")
        #Logger.debug("self.path\t"+self.path)
        # 匹配资源路径
        resource = urlparse.urlparse(self.path).path
        if resource != "/" and resource != "":
            self.send_response(404)
            self.end_headers()  # 注意这个是必不可少的，不然发送不过去
            self.wfile.write('404: Not Found')
            #print "-------------------------------"
            return
        # 获取参数列表的第一个元素
        arguments = dict([(k, v[0] if len(v) > 0 else "") for k, v in argumentList.items()])
        g_requestQueue.put(arguments)
        
        self.send_response(200)
        self.end_headers() 
        self.wfile.write("OK")
        return

class HandleDataThread(threading.Thread): 
    def __init__(self):  
        threading.Thread.__init__(self)
        self.done = False
   
    def run(self):
        global g_requestQueue
        while not self.done:
            statDict = g_requestQueue.get()
            #print "statDict:", statDict
            showStats(statDict)
            time.sleep(0.1)

    def stop(self):
        self.done = True


def showVersion(option, opt_str, value, parser):
    print "nos-rt-server 0.1"
    sys.exit(0)

def sigHandle(signum=0, e=0):
    """signal handle"""

    global pidfile
    global rpcServiceManager
    
    #试图让线程自己中止，方法为线程中增加了变量self.done，
    #每个线程循环时会检测self.done的值，如果self.done变成了真，则会停止。
    #如果线程在6秒后没有停止，则最后会调用os._exit(0)强制停止进程
    allThreads = sorted(threading.enumerate(), key=lambda d:d.name) 
    for t in allThreads:
        if hasattr(t, 'done'):
            print("stop thread(%s)... " % t.name)
            t.done = True
    i = 0
    retryCnt = 3
    for t in allThreads:
        if hasattr(t, 'done'):
            while True:
                if t.isAlive():
                    if i > retryCnt:
                        print("Not waiting for the thread(%s) to stop!" % t.name)
                        break
                    time.sleep(0.1)
                    i = i + 1
                    continue
                else:
                    print("Thread(%s) is stopped." % t.name)
                    break
    g_logFile.close()
    curses.endwin()
    os.system('clear')
    os._exit(0)   

def main():
    global g_serverIpAddr
    global g_port
    global g_screen

    parser = OptionParser()
    parser.add_option("-v", "--version", action="callback", callback=showVersion, nargs=0,
                      help="Show version")

    (options, args) = parser.parse_args()
    
    realPath = os.path.realpath(sys.argv[0])
    if os.path.isdir(realPath):
        modulePath = os.path.abspath(realPath)
    else:
        modulePath = os.path.abspath(os.path.split(realPath)[0])

    signal.signal(signal.SIGINT, sigHandle)
    signal.signal(signal.SIGTERM, sigHandle)
        
    # process data
    handleData = HandleDataThread()
    handleData.start()

    g_screen = curses.initscr()
    os.system('clear')
    g_screen.clear()
    g_screen.border(0)

    deployShowFrame()

    server = HTTPServer((g_serverIpAddr, g_port), HttpHandler)
    #print 'Starting server, use <Ctrl-C> to stop'
    server.serve_forever()
#    curses.endwin()
    os._exit(0)

if __name__ == '__main__':
    main()


