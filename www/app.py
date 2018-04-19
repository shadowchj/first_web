# -*- coding:utf-8 -*-
import Models
import config
import logging,handlers
import asyncio, os, json, time, webstructure,ormstructure
from datetime import datetime
from aiohttp import web
from webstructure import init_jinja2, add_routes, add_static, datetime_filter,logger, response_factory


#日志文件简单配置basicConfig(filename/stream,filemode='a',format,datefmt,level)
logging.basicConfig(level=logging.INFO)



async def init(LOOP):
	'''Application,构造函数 def __init__(self,*,logger=web_logger,loop=None,
	                                     router=None,handler_factory=RequestHandlerFactory,
	                                     middlewares=(),debug=False)
	   使用app时，先将urls注册进router，再用aiohttp.RequestHandlerFactory作为协议簇创建
	   套接字；'''
	#middleware是一种拦截器，一个URL在被某个函数处理前，可以经过一系列的middleware处理
	#详细定义在webstructure.py
	await ormstructure.create_pool(LOOP,**config.configs['db'])
	app = web.Application(loop=LOOP, middlewares=[logger, response_factory])
	init_jinja2(app, filters=dict(datetime=datetime_filter))
	add_routes(app,'handlers')
	add_static(app)
	#用make_handler()创建aiohttp.RequestHandlerFactory，用来处理HTTP协议
	'''用协程创建监听服务，其中LOOP为传入函数的协程，调用其类方法创建一个监听服务，声明如下
	   coroutine BaseEventLoop.create_server(protocol_factory,host=None,port=None,*,
	                                         family=socket.AF_UNSPEC,flags=socket.AI_PASSIVE
	                                         ,sock=None,backlog=100,ssl=None,reuse_address=None
	                                         ,reuse_port=None)
	    await返回后使srv的行为模式和LOOP.create_server()一致'''
	srv = await LOOP.create_server(app.make_handler(), '127.0.0.1', 8888)
	logging.info('sever started at http://127.0.0.1:8888....')
	return srv
#创建协程，LOOP = asyncio.get_event_loop()为asyncio.BaseEventLoop的对象，协程的基本单位
LOOP = asyncio.get_event_loop()
LOOP.run_until_complete(init(LOOP))
LOOP.run_forever()