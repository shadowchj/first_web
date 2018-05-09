# -*- coding:utf-8 -*-
import functools, asyncio, inspect, logging, os, time
from aiohttp import web
from jinja2 import Environment, FileSystemLoader
from ApiError import APIError
from urllib import parse



'''将aiohttp框架进一步封装成更简明使用的web框架

建立视图函数装饰器，用来存储、附带URL信息，这样子便可以直接通过装饰器，将函数映射成视图函数
例：@get
	def View(request):
		return response
	但此时函数View仍未能从request请求中提取相关的参数，
	需自行定义一个处理request请求的类来封装，并把视图函数变为协程'''
def get(path):
	def decorator(func):
		#functools.wraps在装饰器中方便拷贝被装饰函数的签名(使包装的函数有__name__,__doc__属性)
		@functools.wraps(func)
		def wrapper(*args, **kw):
			return func(*args, **kw)
		wrapper.__method__ = 'GET'
		wrapper.__route__ = path
		return wrapper
	return decorator

def post(path):
	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args, **kw):
			return func(*args, **kw)
		wrapper.__method__ = 'POST'
		wrapper.__route__ = path
		return wrapper
	return decorator

#----------------使用Inspect模块，检查视图函数的参数，以下函数的参数fn均为视图函数------------------
#收集没有默认值的命名关键字参数
def get_required_kw_args(fn):
	args = []
	#inspect.signature(函数名).parameters返回函数中可调用的参数(dict形式),其中key为参数名，value为'<parameter '形参'>新式
	params = inspect.signature(fn).parameters
	for name, param in params.items():
		#kind 描述参数值如何绑定到参数，keyword_only表示值必须作为命名关键字参数提供
		if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
			args.append(name)
	return tuple(args)

#获取命名关键字参数
def get_named_kw_args(fn):
	args = []
	params = inspect.signature(fn).parameters
	for name, param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY:
			args.append(name)
	return tuple(args)

#判断有没有命名关键字参数
def has_named_kw_args(fn):
	params = inspect.signature(fn).parameters
	for name, param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY:
			return True

#判断有没有关键字参数
def has_var_kw_arg(fn):
	params = inspect.signature(fn).parameters
	for name, param in params.items():
		# var_keyword：没有绑定到任何其他参数的关键字参数（非命名关键字参数）
		if param.kind == inspect.Parameter.VAR_KEYWORD:
			return True

def has_request_arg(fn):
	params = inspect.signature(fn).parameters
	found = False
	for name, param in params.items():
		if name == 'request':
			found = True
			continue
		'''var_positional :对应 *args的参数，keyword_only：对应命名关键字参数，即*，*args之后的参数
		   var_keyword：对应 **args的参数
		   此处为判断是否有'request'参数，且该参数为可变参数、命名关键字参数、关键字参数之前的最后一个参数'''
		if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
			raise ValueError('request parameter must be the last named parameter in function: %s%s' % (fn.__name__))
	return found

'''request是经aiohttp包装后的对象，其本质是一个HTTP请求，由请求状态(status)，请求首部(header)，内容实体(body)组成
我们需要的参数包含在 内容实体 和 请求状态的URL 中'''
class RequestHandler(object):
	def __init__ (self, app, fn):
		self._app = app
		self._func = fn
		self._has_request_arg = has_request_arg(fn)
		self._has_var_kw_arg = has_var_kw_arg(fn)
		self._has_named_kw_args = has_named_kw_args(fn)
		self._named_kw_args = get_named_kw_args(fn)
		self._required_kw_args = get_required_kw_args(fn)

	#定义__call__()方法可以将类的实例视为函数
	async def __call__(self, request):
		kw = None
		if self._has_var_kw_arg or self._has_named_kw_args or self._has_request_arg:
			if request.method == 'POST':
				#查询是否有头部格式：类似text/html
				if not request.content_type:
					#抛出异常，此处和raise web.HTTPBadRequest等价
					return web.HTTPBadRequest(text='Missing Content-Type.')
				ct = request.content_type.lower()
				if ct.startswith('application/json'):
					#decode json格式(body字段内)
					params = await request.json()
					if not isinstance(params, dict):
						return web.HTTPBadRequest(text='JSON body must be object.')
					kw = params
				#form表单请求的编码形式
				elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
					#直接读取post 的信息，dict-like对象
					params = await request.post()
					kw = dict(**params)
				else:
					return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
			if request.method =='GET':
				#以字符串的形式返回url查询语句 ? 后的键值
				qs = request.query_string
				if qs:
					kw = dict()
					#urllib.parse.parse_qs(qs,keep_blank_values=False,strict_parsing=false,encoding='utf-8',errors='replace')
					#解析作为字符串参数给出的查询字符串，返回字典
					for k,v in parse.parse_qs(qs, True).items():
						kw[k] = v[0]
		if kw is None:
			'''若request中无参数
				request.match_info返回dict对象，可变路由中的可变字段{variable}为参数名，传入的request请求path为值
				例子：可变路由：/a/{name}/c，可匹配的path为：/a/jack/c的request(请求)
				则request.match_info返回{name=jack}
			'''
			kw = dict(**request.match_info)
		else:
			#request中有参数
			if not self._has_var_kw_arg and self._has_named_kw_args:
				#当视图函数没有关键字参数时，移除request中不在命名关键字参数中的参数:
				copy = dict()
				for name in self._named_kw_args:
					if name in kw:
						copy[name] = kw[name]
				kw = copy
			#判断url路径中是否有参数和request中内容实体的参数相同,url路径也要作为参数存入kw中
			for k, v in request.match_info.items():
				if k in kw:
					logging.warning('Duplicate arg name in named arg and kw args: %s' %k)
				kw[k] = v
		#request实例在构造url处理函数中必不可少
		if self._has_request_arg:
			kw['request'] = request
		if self._required_kw_args:
			for name in self._required_kw_args:
				if not name in kw:
					return web.HTTPBadRequest('Missing argument: %s' % name)
		logging.info('call with args: %s' % str(kw))
		try:
			r = await self._func(**kw)
			return r
		except APIError as e:
			return dict(error=e.error, data=e.data, message=e.message)


def add_route(app, fn):
	method = getattr(fn, '__method__', None)
	path = getattr(fn, '__route__', None)
	if path is None or method is None:
		raise ValueError('@get or @post not defined in %s.' % str(fn))
	if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
		fn = asyncio.coroutine(fn)
	#logging.info('%s is a coroutine:%s' % (fn.__name__, asyncio.iscoroutinefunction(fn)))
	logging.info('add route %s %s => %s(%s)' %(method, path, fn.__name__, ','.join(inspect.signature(fn).parameters.keys())))
	app.router.add_route(method, path, RequestHandler(app, fn))

#批量注册视图函数
def add_routes(app, module_name):
	#从右侧检索，返回最后一次出现的位置，若无则返回-1
	n = module_name.rfind('.')
	if n == (-1):
		#__import__('os',globals(),locals(),['path','pip'],0) == from os import path,pip
		mod = __import__(module_name, globals(), locals())
	else:
		name = module_name[n+1:]
		mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
	for attr in dir(mod):
		if attr.startswith('_'):
			continue
		fn = getattr(mod, attr)
		if callable(fn):
			method = getattr(fn, '__method__', None)
			path = getattr(fn, '__route__', None)
			if method and path:
				add_route(app, fn)

#添加静态文件，如image,css,javascript等
def add_static(app):
	#__file__返回当前模块的路径(如果sys.path包含当前模块则返回相对路径，否则绝对路径)
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'static')
	app.router.add_static('/static/', path)
	logging.info('add static %s => %s' % ('/static/', path))

def init_jinja2(app, **kw):
	logging.info('init jinja2...')
	options = dict(
		#自动转义xml/html的特殊字符
		autoescape = kw.get('autoescape', True),
		#代码块的开始、结束标志
		block_start_string = kw.get('block_start_string', '{%'),
		block_end_string = kw.get('block_end_string', '%}'),
		#变量的开始、结束标志
		variable_start_string = kw.get('variable_start_string','{{'),
		variable_end_string = kw.get('variable_end_string','}}'),
		auto_reload = kw.get('auto_reload',True)
		)
	#获取模板文件夹路径
	path = kw.get('path', None)
	if not path:
		path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates')
	#Environment类是jinja2的核心类，用来保存配置、全局对象以及模板文件的路径
	#FileSystemLoader类加载Path路径中的模板文件
	env = Environment(loader = FileSystemLoader(path), **options)
	#过滤器集合
	filters = kw.get('filters', None)
	if filters:
		for name, f in filters.items():
			#filters是Enviroment类的属性：过滤器字典
			env.filters[name] = f
	#app是一个dict-like对象
	app['__template__'] = env

def datetime_filter(t):
	delta = int(time.time() - t)
	if delta < 60:
		return u'one minutes before'
	if delta < 3600:
		return u'%s minutes before' % (delta // 60)
	if delta < 86400:
		return u'%s hours before' % (delta // 3600)
	if delta < 604800:
		return u'%s days before' % (delta // 86400)
	dt = datetime.fromtimestamp(t)
	return u'%s-%s-%s' % (dt.year, dt.month, dt.day)

