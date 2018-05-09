# -*- coding:utf-8 -*-
import Models, config, webstructure, ormstructure, handlers
import asyncio, os, json, time, logging

from ApiError import APIPermissionError
from datetime import datetime
from aiohttp import web
from webstructure import init_jinja2, add_routes, add_static, datetime_filter
from handlers import COOKIE_NAME, cookie2user
from aiohttp.web import middleware

#日志文件简单配置basicConfig(filename/stream,filemode='a',format,datefmt,level)
logging.basicConfig(level=logging.INFO)

#aiohttp V2.3以后的新式写法，教程为旧式写法(也可以混用)，参数handler是视图函数
@middleware
async def logger(request, handler):
	#输出到控制台：收到请求信息的（方法，路径）
	logging.info('Request: %s %s' % (request.method, request.path))
	#继续处理请求
	return await handler(request)

#继续处理经过logger后的请求
@middleware
async def auth(request, handler):
	#输出到控制台：检查请求的信息（方法，路径）
	logging.info('check user: %s %s' % (request.method, request.path))
	request.__user__ = None

	#-----新增一个查看cookies的输出----------------------
	logging.info(request.cookies)

	#获取请求的cookie名为COOKIE_NAME的cookie
	cookie_str = request.cookies.get(COOKIE_NAME)
	#logging.info('cookie_str: %s' % cookie_str)
	#如果保存有该cookie，则验证该cookie，并返回cookie的user（即请求的账户id）
	if cookie_str:
		user = await cookie2user(cookie_str)
		if user:
			logging.info('set current user: %s' % user.email)
			request.__user__ = user
		#此处判定/manage/的子url中的请求是否有权限，如果没有则返回signin登陆界面
	if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
		return web.HTTPFound('/signin')
	if request.path.startswith('/personal/') and request.__user__ is None:
		return web.HTTPFound('signin')
	#继续处理请求
	return await handler(request)

'''
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
'''

#最终处理请求，返回响应给客户端
async def response_factory(app,handler):
	async def response(request):
		logging.info('Response handler....')
		r = await handler(request)
		#如果经过句柄函数（视图函数）handler处理后的请求是stream流响应的实例，则直接返回给客户端
		if isinstance(r, web.StreamResponse):
			logging.info('return StreamResponse.')
			return r
		#如果处理后是字节的实例，则调用web.Response并添加头部返回给客户端
		if isinstance(r, bytes):
			logging.info('return bytes directly.')
			resp = web.Response(body=r)
			resp.content_type = 'application/octet-stream'
			return resp
		#如果处理后是字符串的实例，则需调用web.Response并(utf-8)编码成字节流，添加头部返回给客户端
		if isinstance(r, str):
			logging.info('return str.encode(`utf-8`)')
			#如果开头的字符串是redirect:形式（重定向），则返回重定向后面字符串所指向的页面
			if r.startswith('redirect:'):
				return web.HTTPFound(r[9:])
			resp = web.Response(body=r.encode('utf-8'))
			resp.content_type = 'text/html;charset=utf-8'
			return resp
		#如果处理后是字典的实例.......
		if isinstance(r, dict):
			logging.info('return json or html-models.')
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
			logging.info('return http number')
			resp = web.Response(status=r)

		#-------新添加，需要理解！！！！！-----------------
		if isinstance(r,tuple) and len(r) == 2:
			t, m = r
			if isinstance(t, int) and t >= 100 and t < 600:
				return web.Response(t, str(m))
		#--------------------------------------------------
		
		#默认返回形式
		logging.info('return default response.')
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
	#初始化jinja2模板信息
	init_jinja2(app, filters=dict(datetime=datetime_filter))
	#添加路径
	add_routes(app,'handlers')

	#添加静态路径------------可测试是否能够删除-----------------------
	add_static(app)
	#-----------------------------------------------------------------

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