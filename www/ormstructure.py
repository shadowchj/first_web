# -*- coding:utf-8 -*-
import asyncio, aiomysql, logging

#异步编程原则：系统每一层都必须异步
#aiomysql为MySQL提供了异步IO驱动

'''--------------------------------------------------------------------------'''

'''设计思维：元类 --> 基类 --> 实现类
   元类：用来定义数据库映射到实现类的关系，封装了最底层的sql语句
   基类: 可定义操作数据库的类方法/实例方法，这样子实现类可直接调用该方法而省去了SQL
         语句的直接编写(方法内部封装了sql语句)
         类方法：一般为查找方法，如封装select语句
         实例方法：一般为保存，删除，增加等方法，如insert,delete等语句
   实现类：具体操作的实现
   e.g: metaclass(元类) 中 __select__属性/方法 定义了最基本的sql语句(字符串形式)：select * from tablename...
        base(基类) 中封装成find方法,内部采用__select__属性/方法 实现功能
        实现类 调用父类(base)的find方法即可，不用写SQL语句'''

'''--------------------------------------------------------------------------'''

#定义日志输出函数Log，方便查看
logging.basicConfig(level=logging.INFO)
def log(sql, args=()):
	logging.info('SQL: %s' %sql)


async def create_pool(LOOP, **kw):
	logging.info('create database connection pool...')
	global __pool
	'''
	aiomysql.create_pool(minisize=1,maxsize=10,loop=None,**kw)
	
	a coroutine that creates a pool of connections to MySQL database.
	该方法是一个协程，可创建一个连接MySQL的数据库的POOL
	参数：minisize(int)是该POOL的最小规格，maxsize为最大规格
	      loop:an optional event loop instance
	      **kw:接受所有的字典参数，包括前面的默认参数也可用字典参数形式传入
	'''
	__pool = await aiomysql.create_pool(
		host=kw.get('host','localhost'),
		port=kw.get('port',3306),
		user=kw['user'],
		password=kw['password'],
		db=kw['db'],
		charset=kw.get('charset','utf8'),
		autocommit=kw.get('autocommit',True),
		maxsize=kw.get('maxsize',10),
		minsize=kw.get('minsize',1),
		loop=LOOP)

#封装sql的select语句
async def select(sql, args, size=None):
	#log(sql,args)
	global __pool
	# pool常用的连接方式
	with (await __pool) as conn:
		#DictCursor返回一个字典形式的结果,其余操作和Cursor不变
		cur = await conn.cursor(aiomysql.DictCursor)
		'''sql语句占位符是？，MySQL的占位符是%s
		   execute(query:SQL语句, args=None:SQL语句的参数--元组或列表)'''
		await cur.execute(sql.replace('?','%s'),args or ())
		if size:
			#返回size行内容(元组组成的列表),不足size全部返回,如果没有则返回空列表
			rs = await cur.fetchmany(size)
		else:
			#返回所有行内容
			rs = await cur.fetchall()
		await cur.close()
		#logging.info('rows returned: %s' % len(rs))
		return rs

#封装sql的其它执行语句，比如增加，删除等操作
async def execute(sql,args):
	#log(sql,args)
	with (await __pool) as conn:
		try:
			cur = await conn.cursor()
			await cur.execute(sql.replace('?','%s'),args)
			'''rowcount返查询结果的行数,如果-1则表示没有结果集'''
			affected = cur.rowcount
			await conn.commit()
			await cur.close()
		except BaseException as e:
			raise
		return affected

#函数定义：添加sql语句的占位符:?，在metaclass中的底层运用
def create_args_string(num):
	L = []
	for n in range(num):
		L.append('?')
	return ', '.join(L)

class Field(object):
#column_type为数据类型
	def __init__(self, name, column_type, primary_key, default):
		self.name = name
		self.column_type = column_type
		self.primary_key = primary_key
		self.default = default
	
	def __str__(self):
		return '<%s, %s:%s>' % (self.__class__.__name__, self.column_type, self.name)


class StringField(Field):
	"""映射varchar的StringField"""
	def __init__(self, name=None, primary_key=False, default=None, c_type='varchar(100)'):
		super().__init__(name, c_type, primary_key, default)

class IntField(Field):
	"""映射int的IntField"""
	def __init__(self, name=None, primary_key=False, default=0, c_type='int'):
		super().__init__(name, c_type, primary_key, default)

class FloatField(Field):
	'''映射float值的FloatField'''
	def __init__(self, name=None, primary_key=False, default=0.0, c_type='real'):
		super().__init__(name, c_type, primary_key, default)

class BooleanField(Field):
	"""映射bool值的BooleanField"""
	def __init__(self, name=None, primary_key=False, default=False, c_type='boolean'):
		super().__init__(name, c_type, primary_key, default)

class TextField(Field):
	"""映射文本值的TextField"""
	def __init__(self, name=None, primary_key=False, default=None, c_type='text'):
		super().__init__(name,c_type,primary_key,default)
		

'''-------------------------------分割线-------------------------------------'''
class ModelMetaclass(type):
	''' 元类可以这样子定义:class UpperAttrMetaclass(type),type是Python的内建元类
	可参考[引用]:blog.jobbole.com/21351/ 对元类的一些解释

	类方法的第一个参数是当前的实例，即cls(class?)
	name:future_class_name bases:future_class_parents attrs:future_class_attr
	attrs为类的属性/方法集合,创建User类，则attrs是一个包含User类属性的dict'''
	def __new__(cls, name, bases, attrs):
		#排除Model本身
		if name == 'Model':
			return type.__new__(cls, name, bases, attrs)
		#获取table名称:因为继承了dict所以有get方法，如果没有该类属性则默认tableName=类名
		tableName = attrs.get('__table__', None) or name
		#logging.info('found model: %s (table: %s)' % (name, tableName))
		#获取所有的field(包含主键在内的field):
		mappings = dict()
		#存储主键外的field
		fields = []
		primaryKey = None
		#注意，这里的attrs的key是字段名,value是字段实例,不是字段的具体值
		for k, v in attrs.items():
			if isinstance(v, Field):
				#logging.info(' found mapping: %s ==> %s' % (k, v))
				mappings[k] = v
				if v.primary_key:
					#找到主键
					if primaryKey:
						raise RuntimeError('Duplicate primary key for field: %s' %k)
					primaryKey = k
				else:
					fields.append(k)
		if not primaryKey:
			raise RuntimeError('Primary key not found.')
		for k in mappings.keys():
			#从类属性中删除Field属性，否则，容易造成运行时错误(实例的属性会遮盖类的属性)
			attrs.pop(k)
		#存储主键外的field(多了个单引号``)
		escaped_fields = list(map(lambda f: '`%s`' % f, fields))
		#保存属性和列的映射关系：attrs.__mappings__ = {key字段名1:value字段实例1, key字段名2:value字段实例2....}
		attrs['__mappings__'] = mappings
		attrs['__table__'] = tableName
		#主键属性名
		attrs['__primary_key__'] = primaryKey
		#除主键外的属性名
		attrs['__fields__'] = fields
		#构造默认的sql初始语句
		attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ','.join(escaped_fields), tableName)
		attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ','.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
		#update tablename set 非主键field的实例=? where primarykey = ?
		attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ','.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
		attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
		return type.__new__(cls, name, bases, attrs)


'''Model从dict继承，所以具备有dict的功能，因此可以像引用普通字段那样子写:user['id'] / user.id'''
class Model(dict, metaclass=ModelMetaclass):
	"""定义所有ORM映射的基类Model
	元类metaclass=ModelMetaclass
    这样子，任何继承自Model的类，会自动通过ModelMetaclass扫描映射关系，并存储到
    自身的类属性如__table__、__mappings__中。
    然后，我们往Model类添加class方法，就可以让所有子类调用class方法；
    @classmethod装饰,必须含有默认参数'cls',代表类本身
    添加实例方法则可以让所有子类调用实例方法"""

    # __init__方法会在内部先调用__new__方法,super(类名,self).__init__()，3.0以后的版本可以简写super().__init__()
	def __init__(self, **kw):
		super().__init__(**kw)

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Model' object has no attribute '%s'" % key)

	def __setattr__(self, key, value):
		self[key] = value

	def getValue(self, key):
		return getattr(self, key)

	def getValueOrDefault(self, key):
		#如果找不到则返回None，否则会引发KeyError
		value = getattr(self, key, None)
		if value is None:
			field = self.__mappings__[key]
			if field.default is not None:
				#callable()用于检查一个对象是否是可调用的，True可以调用(不一定成功),False不能调用
				value = field.default() if callable(field.default) else field.default
				logging.debug('using default value for %s: %s' % (key, str(value)))
				setattr(self, key, value)
		return value

	@classmethod
	async def find(cls,pk):
		#定义找主键的类方法，以类的形式返回
		rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
		if len(rs) == 0:
			log('find return none')
			return None
		return cls(**rs[0])

	@classmethod
	async def findAll(cls, where=None, args=None, **kw):
		sql = [cls.__select__]
		if where:
			sql.append('where')
			sql.append(where)
		if args is None:
			args = []
		orderBy = kw.get('orderBy', None)
		if orderBy:
			sql.append('order by')
			sql.append(orderBy)
		limit = kw.get('limit', None)
		if limit is not None:
			sql.append('limit')
			if isinstance(limit, int):
				sql.append('?')
				args.append(limit)
			elif isinstance(limit, tuple) and len(limit) == 2:
				sql.append('?,?')
				args.extend(limit)
			else:
				raise ValueError('Invalid limit values : %s' % str(limit))
		rs = await select(' '.join(sql), args)
		return [cls(**r) for r in rs]

	@classmethod
	async def findNumber(cls, selectField, where=None, args=None):
		sql = ['select %s as _num_ from `%s`' % (selectField, cls.__table__)]
		log(sql)
		if where:
			sql.append('where')
			sql.append(where)
		rs = await select(' '.join(sql), args, 1)
		if len(rs) == 0:
			log('find return none')
			return None
		return rs[0]['_num_']

	async def save(self):
		#设置除主键外的fields
		args = list(map(self.getValueOrDefault, self.__fields__))
		#设置主键的field
		args.append(self.getValueOrDefault(self.__primary_key__))
		#把设置添加进数据库(表内)
		rows = await execute(self.__insert__, args)
		#一条execute语句返回行数为1
		if rows != 1:
			logging.warn('failed to insert record: affected rows: %s' % rows)

	async def delete(self):
		args = self.getValue(self.__primary_key__)
		rows = await execute(self.__delete__, args)
		if rows != 1:
			logging.warn('failed to delete by primary key: affected rows: %s' % rows)

	#自定义了update方法，用来更新初始设置的fields,主键不可更改
	async def update(self):
		args = list(map(self.getValue,self.__fields__))
		args.append(self.getValue(self.__primary_key__))
		rows = await execute(self.__update__,args)
		if rows != 1:
			logging.warn('failed to update by primary key: affected rows: %s' % rows)
