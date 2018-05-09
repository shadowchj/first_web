# -*- coding:utf-8 -*-
from webstructure import get, post
from aiohttp import web
import asyncio, time, re, json, hashlib, base64, logging, markdown2
from Models import Blog, User, next_id, Comment
from ApiError import APIValueError, APIResourceNotFoundError,APIPermissionError, Page
from config import configs

#匹配邮箱
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
#匹配哈希
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')
#cookie的名字
COOKIE_NAME = 'awesession'
#数据库保存的session
_COOKIE_KEY = configs['session']['secret']

def user2cookie(user, max_age):
	#存储cookie的截止时间
	expires = str(int(time.time() + max_age))
	#用户cookie = ID + 密码 + 截止时间 + 数据库的session
	s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
	#加密，进一步包装
	L = [user.id, expires,hashlib.sha1(s.encode('utf-8')).hexdigest()]
	return '-'.join(L)

#定义从cookie中找到user的信息的函数
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
		return user
	except Exception as e:
		logging.exception(e)
		return None

#定义检查请求是否有用户以及该用户是否有权限的函数
def check_admin(request):
	if request.__user__ is None or not request.__user__.admin:
		raise APIPermissionError()

def get_page_index(page_str):
	p = 1
	try:
		p = int(page_str)
	except ValueError as e:
		pass
	if p < 1:
		p = 1
	return p

#text文本到html格式的转换（防止一些特殊符号的时候不会是乱码）
def text2html(text):
	lines = map(lambda s: '<p>%s</p>' % s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'), filter(
		lambda s: s.strip() != '', text.split('\n')))
	return ''.join(lines)

'''-----思路： 前端页面带有模板，具体操作响应用后端API处理，然后返回响应的页面'''

#主页(根url)
@get('/')
async def index(*, page='1'):
	page_index = get_page_index(page)
	num = await Blog.findNumber('count(id)') 
	page = Page(num)
	if num == 0:
		blogs = []
	else:
		blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
	return {
		'__template__': 'blogs.html',
		'blogs': blogs,
		'page':page
	}

#注册页面
@get('/register')
def register():
	return {
		'__template__': 'register.html'
	}

#登陆页面
@get('/signin')
def signin():
	return {
		'__template__': 'signin.html'
	}

#注销页面
@get('/signout')
def signout(request):
	referer = request.headers.get('Referer')
	r = web.HTTPFound(referer or '/')
	r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
	logging.info('user signed out.')
	return r

#获取某篇博客具体内容页面（包括评论等）
@get('/blog/{id}')
async def get_blog(id):
	logging.info('blog_id: %s' % id)
	blog = await Blog.find(id)
	comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
	for c in comments:
		c.html_content = text2html(c.content)
	# markdown将txt转化成为html格式
	blog.html_content = markdown2.markdown(blog.content)
	return {
		'__template__': 'blog.html',
		'blog':blog,
		'comments': comments
	}





'''----------------管理员页面------------------------------------------------'''

#返回重定向url ===> manage/comments
@get('/manage/')
def manage():
	return 'redirect:/manage/comments'

#管理评论列表页
@get('/manage/comments')
def manage_comments(*, page='1'):
	return{
		'__template__': 'manage_comments.html',
		'page_index': get_page_index(page)
	}

#博客列表页
@get('/manage/blogs')
def manage_blogs(*, page='1'):
	return{
		'__template__': 'manage_blogs.html',
		'page_index': get_page_index(page)
	}

#创建博客页，action ===> /api/blogs
@get('/manage/blogs/create')
def manage_create_blog():
	return{
		'__template__': 'manage_blog_edit.html',
		'id':'',
		'action':'/api/blogs'
	}

#修改某篇博客页，action ===> /api/blogs/{id}
@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
	return{
		'__template__': 'manage_blog_edit.html',
		'id': id,
		'action': '/api/blogs/%s' % id
	}

#用户列表页
@get('/manage/users')
def manage_users(*, page='1'):
	return{
		'__template__': 'manage_users.html',
		'page_index':get_page_index(page)
	}

#管理个人资料
@get('/personal/edit')
async def edit_user():
	return{
		'__template__': 'user_edit.html'
	}

#-------------------------------------后端api----------------------------------------

#获取评论
@get('/api/comments')
async def api_comments(*, page='1'):
	page_index = get_page_index(page)
	num = await Comment.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, comments=())
	comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	return dict(page=p, comments=comments)

#删除评论，需要检查是否有权限
@post('/api/comments/{id}/delete')
async def api_delete_comments(id, request):
	check_admin(request)
	c = await Comment.find(id)
	if c is None:
		raise APIResourceNotFoundError('Comment')
	await c.delete()
	return dict(id=id)

#创建某篇博客的评论
@post('/api/blogs/{id}/comments')
async def api_create_comment(id, request, *, content):
	user = request.__user__
	if user is None:
		raise APIPermissionError('please signin first.')
	if not content or not content.strip():
		raise APIValueError('content')
	blog = await Blog.find(id)
	if blog is None:
		raise APIResourceNotFoundError('Blog')
	comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image, content=content.strip())
	await comment.save()
	return comment

#获取博客
@get('/api/blogs')
async def api_blogs(*, page='1'):
	page_index = get_page_index(page)
	num = await Blog.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, blogs=())
	blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	return dict(page=p, blogs=blogs)

#获取某篇博客
@get('/api/blogs/{id}')
async def api_get_blog(*, id):
	blog = await Blog.find(id)
	return blog

#修改某篇博客，由上面 /manage/blogs/edit中action跳转处理
@post('/api/blogs/{id}')
async def api_update_blog(id, request, *, name, summary, content):
	check_admin(request)
	if not name or not name.strip():
		raise APIValueError('name', 'name cannot be empty.')
	if not summary or not summary.strip():
		raise APIValueError('summary', 'summary cannot be empty.')
	if not content or not content.strip():
		raise APIValueError('content', 'content cannot be empty.')
	blog = await Blog.find(id)
	blog.name = name.strip()
	blog.summary = summary.strip()
	blog.content = content.strip()
	await blog.update()
	return blog

#删除某篇博客
@post('/api/blogs/{id}/delete')
async def api_delete_blog(request, *, id):
	check_admin(request)
	blog = await Blog.find(id)
	await blog.delete()
	return dict(id=id)

#创建博客，由/manage/blogs中action跳转处理
@post('/api/blogs')
async def api_create_blog(request, *, name, summary, content):
	check_admin(request)
	if not name or not name.strip():
		raise APIValueError('name', 'name cannot be empty.')
	if not summary or not summary.strip():
		raise APIValueError('summary', 'summary cannot be empty.')
	if not content or not content.strip():
		raise APIValueError('content', 'content cannot be empty.')
	blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image,
		name=name.strip(), summary=summary.strip(), content=content.strip())
	await blog.save()
	return blog

#登陆验证邮箱与密码是否正确，由登陆页get/signin中的action跳转至此处理
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

#获取用户
@get('/api/users')
async def api_get_users(*, page='1'):
	page_index = get_page_index(page)
	num = await User.findNumber('count(id)')
	p = Page(num, page_index)
	if num == 0:
		return dict(page=p, users=())
	users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
	for u in users:
		u.passwd = '******'
	return dict(page=p, users=users)

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
	user = User(id=uid, name=name.strip(),email=email,passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(),image='http://www.gravatar.com/avatar/%s?d=robohash&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
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

@post('/api/update_user')
async def api_update_user(*, id, name, oldpasswd, newpasswd):
	if not name or not name.strip():
		raise APIValueError('name')
	if not oldpasswd or not _RE_SHA1.match(oldpasswd):
		raise APIValueError('oldpasswd')
	if not newpasswd or not _RE_SHA1.match(newpasswd):
		raise APIValueError('newpasswd')
	user = await User.find(id)
	sha1 = hashlib.sha1()
	sha1.update(id.encode('utf-8'))
	sha1.update(b':')
	sha1.update(oldpasswd.encode('utf-8'))
	if user.passwd != sha1.hexdigest():
		raise APIValueError('passwd', '原密码输入错误')
	user.name = name.strip()
	sha1_passwd = '%s:%s' % (id, newpasswd)
	user.passwd = hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest()
	await user.update()
	r = web.Response()
	r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
	user.passwd = '******'
	r.content_type = 'application/json'
	r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
	return r
