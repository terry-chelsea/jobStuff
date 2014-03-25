#!/usr/bin/env python
# -*- coding:UTF-8

'''
Created on 2013-08-27

@author: wudong
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

g_serverIpAddr = '0.0.0.0'
g_port = 5737


g_requestQueue = Queue.Queue(maxsize = 10000)
g_screen = curses.initscr()


def showStats(statDict):
    global g_screen

    keyPosDict = {
     'DATE' : [1,6],
     'LOAD' : [2,6],
     'CPU' : [3,6]
     }
    for key in statDict:
        if key in keyPosDict:
            value = statDict[key]
            pos = keyPosDict[key]
            g_screen.addstr(pos[0], pos[1], "%s: %s" % (key, value))
    g_screen.refresh()

class HttpHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        return

    def do_GET(self):
        self.__dealWithRequest()
        return

    def do_POST(self):
        self.__dealWithRequest()
		print "hello world"

        return

    def __dealWithRequest(self):
        Logger = logging.getLogger()

		req = self.request.recv(1024)
	    print ret

        #　获取的参数是一个字典，并且value是一个数组,形如{'q': ['abc'], 'p': ['123'], 'xx': ['']}
        #　参数True会解析出没有value的key
        argumentList = urlparse.parse_qs(urlparse.urlparse(self.path).query, True)
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
#        arguments = dict([(k, v[0] if len(v) > 0 else "") for k, v in argumentList.items()])
#        g_requestQueue.put(arguments)
       	


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
    retryCnt = 5
    for t in allThreads:
        if hasattr(t, 'done'):
            while True:
                if t.isAlive():
                    if i > retryCnt:
                        print("Not waiting for the thread(%s) to stop!" % t.name)
                        break
                    time.sleep(0.2)
                    i = i + 1
                    continue
                else:
                    print("Thread(%s) is stopped." % t.name)
                    break
    curses.endwin()
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

    os.system('clear')
    g_screen.clear()
    g_screen.border(0)
    
    server = HTTPServer((g_serverIpAddr, g_port), HttpHandler)
    print 'Starting server, use <Ctrl-C> to stop'
    server.serve_forever()
    curses.endwin()
    os._exit(0)

if __name__ == '__main__':
    main()


