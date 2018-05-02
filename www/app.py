# -*- coding:utf-8 -*-
import Models
import config
import logging,handlers
import asyncio, os, json, time, webstructure,ormstructure
from datetime import datetime
from aiohttp import web
from webstructure import init_jinja2, add_routes, add_static, datetime_filter
from handlers import user2cookie,COOKIE_NAME
from aiohttp.web import middleware

#日志文件简单配置basicConfig(filename/stream,filemode='a',format,datefmt,level)
logging.basicConfig(level=logging.INFO)

#aiohttp V2.3以后的新式写法，教程为旧式写法(也可以混用)，参数handler是视图函数
@middleware
async def logger(request, handler):
	logging.info('Request: %s %s' % (request.method, request.path))
	#继续处理请求
	return await handler(request)

@middleware
async def auth(request, handler):
	logging.info('check user: %s %s' % (request.method, request.path))
	request.__user__ = None
	cookie_str = request.cookies.get(COOKIE_NAME)
	if cookie_str:
		user = await cookie2user(cookie_str)
		if user:
			logging.info('set current user: %s' % user.email)
			request.__user__ = user
		if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
			return web.HTTPFound('signin')
	return await handler(request)

@middleware
async def parse_data(request, handler):
	if request.method == 'POST':
		if request.content_type.startswith('application/json'):
			request.__data__ = await request.json()
			logging.info('request json: %s' % str(request.__data__))
		elif request.content_type.startswith('application/x-www-form-urlencoded'):
			request.__data__ = await request.post()
			logging.info('request form: %s' % str(request.__data__))
	return await handler(request)

async def response_factory(app,handler):
	async def response(request):
		r = await handler(request)
		if isinstance(r, web.StreamResponse):
			return r
		if isinstance(r, bytes):
			resp = web.Response(body=r)
			resp.content_type = 'application/octet-stream'
			return resp
		if isinstance(r, str):
			resp = web.Response(body=r.encode('utf-8'))
			resp.content_type = 'text/html;charset=utf-8'
			return resp
		if isinstance(r,dict):
			#在后续构造视图函数返回值时，会加入__template__值，用以选择渲染的模板
			template = r.get('__template__', None)
			if template is None:
				'''不带模板信息，返回json对象
				ensure_ascii:默认True，仅能输出ascii格式数据。故设置为False
				#default: r对象会先被传入default中的函数进行处理，然后才被序列化为json对象
				__dict__: 以dict形式返回对象属性和值的映射，一般的class实例都有一个__dict__属性'''
				resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda obj: obj.__dict__).encode('utf-8'))
				resp.content_type = 'application/json;charset=utf-8'
				return resp
			else:
				'''get_template()方法返回Template对象，调用其render()方法传入r渲染模板'''
				r['__user__'] = request.__user__
				resp = web.Response(body=app['__template__'].get_template(template).render(**r).encode('utf-8'))
				resp.content_type = 'text/html;charset=utf-8'
				return resp
		#返回响应码
		if isinstance(r, int) and (600>r>=100):
			resp = web.Response(status=r)
		#default
		resp = web.Response(body=str(r).encode('utf-8'))
		resp.content_type = 'text/plain;charset=utf-8'
		return resp
	return response



async def init(LOOP):
	'''Application,构造函数 def __init__(self,*,logger=web_logger,loop=None,
	                                     router=None,handler_factory=RequestHandlerFactory,
	                                     middlewares=(),debug=False)
	   使用app时，先将urls注册进router，再用aiohttp.RequestHandlerFactory作为协议簇创建
	   套接字；'''
	#middleware是一种拦截器，一个URL在被某个函数处理前，可以经过一系列的middleware处理
	#详细定义在webstructure.py
	await ormstructure.create_pool(LOOP,**config.configs['db'])
	app = web.Application(loop=LOOP, middlewares=[logger, auth, response_factory])
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
if __name__ == '__main__':
	#创建协程，LOOP = asyncio.get_event_loop()为asyncio.BaseEventLoop的对象，协程的基本单位
	LOOP = asyncio.get_event_loop()
	LOOP.run_until_complete(init(LOOP))
	LOOP.run_forever()