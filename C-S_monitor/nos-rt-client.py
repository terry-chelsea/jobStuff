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

g_serverIpAddr = '0.0.0.0'
g_port = 5737

def ioStats(devName):
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
    f = file(statFile)
    line = f.read()
    f.close()
    line = line.strip()
    cells = line.split()
    print "cells:", cells
    cells = [ int(i) for i in cells ]
    return cells
 
def cpuStats():
    """
    user (432661) 从系统启动开始累计到当前时刻，用户态的CPU时间（单位：jiffies） ，不包含 nice值为负进程。1jiffies=0.01秒
    nice (13295) 从系统启动开始累计到当前时刻，nice值为负的进程所占用的CPU时间（单位：jiffies）
    system (86656) 从系统启动开始累计到当前时刻，核心时间（单位：jiffies）
    idle (422145968) 从系统启动开始累计到当前时刻，除硬盘IO等待时间以外其它等待时间（单位：jiffies）
    iowait (171474) 从系统启动开始累计到当前时刻，硬盘IO等待时间（单位：jiffies） ，
    irq (233) 从系统启动开始累计到当前时刻，硬中断时间（单位：jiffies）
    softirq (5346) 从系统启动开始累计到当前时刻，软中断时间（单位：jiffies）
    CPU时间=user+system+nice+idle+iowait+irq+softirq
    """
    try:  
        fd = open("/proc/stat", 'r')  
        lines = fd.readlines()  
    finally:  
        if fd:  
            fd.close()  
    for line in lines:  
        l = line.split()  
        if len(l) < 5:
            continue
        if l[0].startswith('cpu'):
            return [ int(i) for i in l[1:] ]
    return []


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
	sys.exit(-1)

def showVersion(option, opt_str, value, parser):
    print "nos-rt-client 0.1"
    sys.exit(0)

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
    ioStatsList1 = ioStats('sda')
    
    cpuStatsList1 = cpuStats()
    cpuTotalTime1 = 0
    for i in cpuStatsList1:
        cpuTotalTime1 = cpuTotalTime1 + i
    cpuUseTime1 = cpuStatsList1[0] + cpuStatsList1[1] + cpuStatsList1[2]
    
    startTime = time.time()
    while True:
        time.sleep(1)
        ioStatsList2 = ioStats('sda')
        endTime = time.time()
        rps = round((ioStatsList2[0] - ioStatsList1[0]) /(endTime - startTime))
        wps = round((ioStatsList2[4] - ioStatsList1[4]) /(endTime - startTime))
        ioUtils = round((ioStatsList2[9] - ioStatsList1[9])/((endTime - startTime)*10))
        print "%d, %d, %d%%" % (rps, wps, ioUtils)

        cpuStatsList2 = cpuStats()
        cpuTotalTime2 = 0
        for i in cpuStatsList2:
            cpuTotalTime2 = cpuTotalTime2 + i
        cpuUseTime2 = cpuStatsList2[0] + cpuStatsList2[1] + cpuStatsList2[2]
        cpuUtils = 100*(cpuUseTime2 - cpuUseTime1) / (cpuTotalTime2 - cpuTotalTime1)        
        print "cpu: %s%%" % cpuUtils

        cpuTotalTime1 = cpuTotalTime2
        cpuUseTime1 = cpuUseTime2        
        startTime = endTime
        ioStatsList1 = ioStatsList2

if __name__ == '__main__':
    main()

