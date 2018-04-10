# -*- coding:utf-8 -*-

import logging
import asyncio, os, json, time
from datetime import datetime
from aiohttp import web

#日志文件简单配置basicConfig(filename/stream,filemode='a',format,datefmt,level)
logging.basicConfig(level=logging.INFO)
#index界面，类型为html
def index(request):
	return web.Response(body=b'<h1>Awesome</h1>', content_type='text/html')

async def init(LOOP):
	'''Application,构造函数 def __init__(self,*,logger=web_logger,loop=None,
	                                     router=None,handler_factory=RequestHandlerFactory,
	                                     middlewares=(),debug=False)
	   使用app时，先将urls注册进router，再用aiohttp.RequestHandlerFactory作为协议簇创建
	   套接字；'''
	app = web.Application(loop=LOOP)
	#将处理函数注册到app.route中
	app.router.add_route('GET', '/', index)
	#用make_handler()创建aiohttp.RequestHandlerFactory，用来处理HTTP协议
	'''用协程创建监听服务，其中LOOP为传入函数的协程，调用其类方法创建一个监听服务，声明如下
	   coroutine BaseEventLoop.create_server(protocol_factory,host=None,port=None,*,
	                                         family=socket.AF_UNSPEC,flags=socket.AI_PASSIVE
	                                         ,sock=None,backlog=100,ssl=None,reuse_address=None
	                                         ,reuse_port=None)
	    await使srv的行为模式和LOOP.create_server()一致'''
	srv = await LOOP.create_server(app.make_handler(), '127.0.0.1', 8888)
	logging.info('sever started at http://127.0.0.1:8888....')
	return srv
#创建协程，LOOP = asyncio.get_event_loop()为asyncio.BaseEventLoop的对象，协程的基本单位
LOOP = asyncio.get_event_loop()
LOOP.run_until_complete(init(LOOP))
LOOP.run_forever()