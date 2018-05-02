# -*- coding:utf-8 -*-
from webstructure import get, post
from aiohttp import web
import asyncio, time, re, json, hashlib, base64, logging
from Models import Blog, User, next_id, Comment
from ApiError import APIValueError, APIResourceNotFoundError
from config import configs

#匹配邮箱
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs['session']['secret']

def user2cookie(user, max_age):
	#存储cookie的截止时间
	expires = str(int(time.time() + max_age))
	s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
	L = [user.id, expires,hashlib.sha1(s.encode('utf-8')).hexdigest()]
	return '-'.join(L)

async def cookie2user(cookie_str):
	if not cookie_str:
		return None
	try:
		L = cookie_str.split('-')
		if len(L) != 3:
			return None
		uid, expires, sha1 = L
		#如果截止时间小于现在的时间，代表cookie过期了
		if int(expires) < time.time():
			return None
		user = await User.find(uid)
		if user is None:
			return None
		s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
		if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
			logging.info('invalid sha1')
			return None
		user.passwd = '******'
	except Exception as e:
		logging.exception(e)
		return None

@get('/')
def index(request):
	summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
	blogs = [
		Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
		Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
		Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
	]
	return {
		'__template__': 'blogs.html',
		'blogs': blogs
	}

@get('/register')
def register():
	return {
		'__template__': 'register.html'
	}

@get('/signin')
def signin():
	return {
		'__template__': 'signin.html'
	}

#登陆验证邮箱与密码是否正确
@post('/api/authenticate')
async def authenticate(*, email, passwd):
	if not email:
		raise APIValueError('email', 'Invalid email.')
	if not passwd:
		raise APIValueError('passwd','Invalid password.')
	users = await User.findAll('email=?', [email])
	if len(users) == 0:
		raise APIValueError('email', 'Email not exist.')
	user = users[0]
	#check passwd
	sha1 = hashlib.sha1()
	sha1.update(user.id.encode('utf-8'))
	sha1.update(b':')
	sha1.update(passwd.encode('utf-8'))
	if user.passwd != sha1.hexdigest():
		raise APIValueError('passwd', 'Invalid passwd.')
	# authenticate ok, set cookie
	r = web.Response()
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	user.passwd = '******'
	r.content_type = 'application/json'
	r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
	return r

@get('/signout')
def signout(request):
	referer = request.headers.get('Referer')
	r = web.HTTPFound(referer or '/')
	r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
	logging.info('user signed out.')
	return r

#注册页面时需要填写的信息：邮箱，用户名，密码
@post('/api/users')
async def api_register_user(*, email, name, passwd):
	#str.strip([chars])移除字符串头尾指定的字符(默认空格)
	if not name or not name.strip():
		raise APIValueError('name')
	if not email or not _RE_EMAIL.match(email):
		raise APIValueError('email')
	if not passwd or not _RE_SHA1.match(passwd):
		raise APIValueError('passwd')
	users = await User.findAll('email=?', [email])
	if len(users) > 0:
		raise APIValueError('register:failed', 'email', 'Email is already in use.')
	uid = next_id()
	# 加密形式:next_id():passwd，数据库中保存其摘要hexdigest()。与上面验证的时候要保持一致
	sha1_passwd = '%s:%s' % (uid, passwd)
	user = User(id=uid, name=name.strip(),email=email,passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),image='block')
	await user.save()
	r = web.Response()
	#set_cookie(name,value,*,path='/',expires=None,domain=None,max_age=None,secure=None,httponly=None,version=None)
	#name:cookie名称(str),value:cookie值(str),expires在http1.1被遗弃，使用max_age代替
	#path(str):指定Cookie应用于的url的子集，默认'/'
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	user.passwd = '******'
	r.content_type = 'application/json'
	r.body = json.dumps(users, ensure_ascii=False).encode('utf-8')
	return r
	