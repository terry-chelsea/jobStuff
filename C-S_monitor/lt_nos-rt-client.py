#!/usr/bin/env python
# -*- coding:UTF-8

'''
Created on 2014-03-20

@author: hztangcheng
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
import socket
import httplib
import urllib

g_serverIpAddr = '0.0.0.0'
g_port = 5737

g_interval = 1

g_hostname = ''
gNetworkCard = "eth0"
gDiskName = "sda"
gwatchPort = []

def getFileContents(name) : 
    try : 
        fp = file(name)
        lines = fp.readlines()
        fp.close()
    except BaseException , e : 
        print "read from file %s failed : %s" %(name , str(e))
        return None

    return lines;

def diskRawStats(devName):
    '''返回以fieldName为列表的一个数组
    '''
    fieldName = [
         'reads_completed',
         'reads_merged',
         'sectors_read',
         'time_spent_reading',
         'writes_completed',
         'writes_merged',
         'sectors_written',
         'time_spent_writing',
         'progress_ios',
         'time_spent_doing_io',
         'weighted_time_spent_doing_io' ]
    
    statFile = '/sys/block/%s/stat' % devName
    lines = getFileContents(statFile)
    line = lines[0].strip()
    cells = line.split()
    #print "cells:", cells
    cells = [ int(i) for i in cells ]
    return cells

def diskStatsGenerator(devName):
    '''返回上一次调用到这次调用期间的 [ 读速率、写速率、磁盘利用率 ]
    '''

    time1 = time.time()
    cells1 = diskRawStats(devName)
    yield [0, 0, 0]
    
    while True:
        cells2 = diskRawStats(devName)
        time2 = time.time()
        interval = time2 - time1
        
        readRate = int(round((cells2[0] - cells1[0]) /interval))
        writeRate = int(round((cells2[4] - cells1[4]) /interval))
        diskUtils = int(round((cells2[9] - cells1[9])/(interval*10)))
        yield [readRate, writeRate, diskUtils]
        time1 = time2
        cells1 = cells2

def tcpStats() : 
    establisheds = 0
    timeWait = 0
    lines = getFileContents('/proc/net/tcp')
    for line in lines[1:] : 
        line = line.strip()
       	cells = line.split()
        localAddr = cells[1].split(":")
        port = int(localAddr[1] , 16)
        status = int(cells[3] , 16)
        if not gwatchPort or port in gwatchPort : 
            if status == 1 : 
			    establisheds += 1
            elif status == 6 : 
			    timeWait += 1

    return [establisheds , timeWait]

def cpuRawStats():
    """
    返回如下的一个数组：
    
    user (432661) 从系统启动开始累计到当前时刻，用户态的CPU时间（单位：jiffies） ，不包含 nice值为负进程。1jiffies=0.01秒
    nice (13295) 从系统启动开始累计到当前时刻，nice值为负的进程所占用的CPU时间（单位：jiffies）
    system (86656) 从系统启动开始累计到当前时刻，核心时间（单位：jiffies）
    idle (422145968) 从系统启动开始累计到当前时刻，除硬盘IO等待时间以外其它等待时间（单位：jiffies）
    iowait (171474) 从系统启动开始累计到当前时刻，硬盘IO等待时间（单位：jiffies） ，
    irq (233) 从系统启动开始累计到当前时刻，硬中断时间（单位：jiffies）
    softirq (5346) 从系统启动开始累计到当前时刻，软中断时间（单位：jiffies）
    CPU时间=user+system+nice+idle+iowait+irq+softirq
    """

    lines = getFileContents('/proc/stat')
    for line in lines:  
        l = line.split()  
        if len(l) < 5:
            continue
        if l[0].startswith('cpu'):
            return [ int(i) for i in l[1:] ]
    return []

def cpuStatsGenerator():
    '''返回上一次调用到这次调用期间的CPU占用率
    '''

    time1 = time.time()
    cells1 = cpuRawStats()
    yield [0, 0, 0]
    
    while True:
        cells2 = cpuRawStats()
        time2 = time.time()
        interval = time2 - time1

        cpuTotalTime1 = 0
        for i in cells1:
            cpuTotalTime1 = cpuTotalTime1 + i

        cpuTotalTime2 = 0    
        for i in cells2:
            cpuTotalTime2 = cpuTotalTime2 + i
            
        cpuUseTime1 = cells1[0] + cells1[1] + cells1[2]
        cpuUseTime2 = cells2[0] + cells2[1] + cells2[2]
        
        cpuUtils = int(100*(cpuUseTime2 - cpuUseTime1) / (cpuTotalTime2 - cpuTotalTime1))
        yield cpuUtils
        
        time1 = time2
        cells1 = cells2

def netRawStats(devName):
    '''
          |   Receive                                                |  Transmit
     face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    '''
    
    lines = getFileContents('/proc/net/dev')
    for line in lines:
        line = line.strip()
        l = line.split()
        if len(l) < 17:
            continue
        
        if l[0]=='%s:' % devName :
            return [ int(i) for i in l[1:] ]
    return []


def netStatsGenerator(devName):
    '''返回上一次调用到这次调用期间的 [ 接收带宽、发送带宽、每秒接收的包数，每秒发送的包数 ]
    '''

    time1 = time.time()
    cells1 = netRawStats(devName)
    yield [0, 0, 0]
    
    while True:
        cells2 = netRawStats(devName)
        time2 = time.time()
        interval = time2 - time1
        
        recvBandwidth = int(round((cells2[0] - cells1[0]) /interval))
        sendBandwidth = int(round((cells2[8] - cells1[8]) /interval))
        recvPacksRate = int(round((cells2[1] - cells1[1])/interval))
        recvSendRate = int(round((cells2[9] - cells1[9])/interval))
        
        yield [recvBandwidth, sendBandwidth, recvPacksRate, recvSendRate]
        time1 = time2
        cells1 = cells2

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
    os._exit(0)

def showVersion(option, opt_str, value, parser):
    print "nos-rt-client 0.1"
    sys.exit(0)

def sendStatsToServer(statsDict) :
    
    global g_serverIpAddr
    global g_port
    global g_hostname

    statsDict['hostname'] = g_hostname    
    try : 
        conn = httplib.HTTPConnection(g_serverIpAddr , port = g_port , timeout=10)
        params = urllib.urlencode(statsDict)
        #headers = {}
        #print "params:", params
        #conn.request("POST" , "/" ,params , headers)
        print params
        url = '/?' + params
        conn.request("GET", url)
        ret = conn.getresponse()
        print ret.reason
    except BaseException , e : 
        print "Send URL to server %s:%d failed : %s " %(g_serverIpAddr , g_port , str(e))
        return False
    
    return True

def main():
    global g_serverIpAddr
    global g_port
    global g_screen

    global g_hostname

    g_hostname = socket.gethostname()

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

    diskGen = diskStatsGenerator(gDiskName)
    diskGen.next()

    cpuGen = cpuStatsGenerator()
    cpuGen.next()

    netGen = netStatsGenerator(gNetworkCard)
    netGen.next()
    
    
    while True:
        time.sleep(1)

        rps, wps, diskUtils = diskGen.next()
        print "diskstat: %d, %d, %d%%" % (rps, wps, diskUtils)
        cpuUtils = cpuGen.next()
        print "CPU: %d%%" % cpuUtils
        netRecvBytes, netSendBytes, netRecvPacks, netSendPacks =  netGen.next()
        print "NET: %d, %d, %d ,%d" % (netRecvBytes, netSendBytes, netRecvPacks, netSendPacks)

        established , timeWait = tcpStats()
        print "TCP : %d, %d" % (established , timeWait)

        statsDict = {'diskUtils' : diskUtils,
                     'diskReadRate' : rps,
                     'diskWriteRate' : wps,
                     'cpuUtils' : cpuUtils,
                     'netRecvBytes' : netRecvBytes,
                     'netSendBytes' : netSendBytes,
                     'netRecvPacks': netRecvPacks, 
                     'netSendPacks' : netSendPacks,
					 'established' : established,
					 'TIME_WAIT' : timeWait
                    }
        
        sendStatsToServer(statsDict)

if __name__ == '__main__':
    main()

