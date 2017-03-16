from __future__ import absolute_import,unicode_literals

import io
import os
import sys
import json
import time
import types
import msgpack
import functools
import itertools
import threading
import traceback

from binascii import hexlify

import synapse.exc as s_exc

from synapse.exc import *
from synapse.compat import enbase64, debase64, canstor

class NoValu:pass
novalu = NoValu()

def now():
    return int( time.time() * 1000 )

def guid():
    return hexlify(os.urandom(16)).decode('utf8')

def tufo(typ,**kwargs):
    return (typ,kwargs)

def msgenpack(obj):
    return msgpack.dumps(obj, use_bin_type=True, encoding='utf8')

def msgunpack(byts):
    return msgpack.loads(byts, use_list=False, encoding='utf8')

def msgpackfd(fd):
    unpk = msgpack.Unpacker(fd, use_list=False, encoding='utf8')
    for mesg in unpk:
        yield mesg

def vertup(vstr):
    '''
    Convert a version string to a tuple.

    Example:

        ver = vertup('1.3.30')

    '''
    return tuple([ int(x) for x in vstr.split('.') ])

def genpath(*paths):
    path = os.path.join(*paths)
    path = os.path.expanduser(path)
    path = os.path.expandvars(path)
    return os.path.abspath(path)

def reqpath(*paths):
    path = genpath(*paths)
    if not os.path.isfile(path):
        raise NoSuchFile(path)
    return path

def reqfile(*paths, **opts):
    path = genpath(*paths)
    if not os.path.isfile(path):
        raise NoSuchFile(path)
    opts.setdefault('mode','rb')
    return io.open(path,**opts)

def reqlines(*paths, **opts):
    '''
    Open a file and yield lines of text.

    Example:

        for line in reqlines('foo.txt'):
            dostuff(line)

    NOTE: This API is used as a performance optimization
          over the standard fd line iteration mechanism.
    '''
    opts.setdefault('mode','r')
    opts.setdefault('encoding','utf8')

    rem = None
    with reqfile(*paths,**opts) as fd:

        bufr = fd.read(10000000)
        while bufr:

            if rem != None:
                bufr = rem + bufr

            lines = bufr.split('\n')
            rem = lines[-1]

            for line in lines[:-1]:
                yield line.strip()

            bufr = fd.read(10000000)

            if rem != None:
                bufr = rem + bufr

def reqbytes(*paths):
    with reqfile(*paths) as fd:
        return fd.read()

def genfile(*paths):
    '''
    Create or open ( for read/write ) a file path join.
    '''
    path = genpath(*paths)
    gendir( os.path.dirname(path) )
    if not os.path.isfile(path):
        return io.open(path,'w+b')
    return io.open(path,'r+b')

def gendir(*paths,**opts):
    mode = opts.get('mode',0o700)
    path = genpath(*paths)
    if not os.path.isdir(path):
        os.makedirs(path,mode=mode)
    return path

def reqdir(*paths):
    path = genpath(*paths)
    if not os.path.isdir(path):
        raise NoSuchDir(path=path)
    return path

def jsload(*paths):
    with genfile(*paths) as fd:
        byts = fd.read()
        if not byts:
            return None

        return json.loads(byts.decode('utf8'))

def gentask(func,*args,**kwargs):
    return (func,args,kwargs)

def jssave(js,*paths):
    path = genpath(*paths)
    with io.open(path,'wb') as fd:
        fd.write( json.dumps(js).encode('utf8') )

def verstr(vtup):
    '''
    Convert a version tuple to a string.
    '''
    return '.'.join([ str(v) for v in vtup ])

def excinfo(e):
    '''
    Populate err,errmsg,errtrace info from exc.
    '''
    tb = sys.exc_info()[2]
    path,line,name,sorc = traceback.extract_tb(tb)[-1]
    ret = {
        'err':e.__class__.__name__,
        'errmsg':str(e),
        'errfile':path,
        'errline':line,
    }

    if isinstance(e,SynErr):
        ret['errinfo'] = e.errinfo

    return ret

def synerr(excname,**info):
    '''
    Return a SynErr exception.  If the given name
    is not known, fall back on the base class.
    '''
    info['excname'] = excname
    cls = getattr(s_exc,excname,s_exc.SynErr)
    return cls(**info)

def errinfo(name,mesg):
    return {
        'err':name,
        'errmsg':mesg,
    }

def chunks(item,size):
    '''
    Divide an iterable into chunks.
    '''
    # use islice if it's a generator
    if type(item) == types.GeneratorType:

        while True:

            chunk = tuple(itertools.islice(item,size))
            if not chunk:
                return

            yield chunk

    # otherwise, use normal slicing

    off = 0

    while True:

        chunk = item[off:off+size]
        if not chunk:
            return

        yield chunk

        off += size

def reqStorDict(x):
    '''
    Raises BadStorValu if any value in the dict is not compatible
    with being stored in a cortex.
    '''
    for k,v in x.items():
        if not canstor(v):
            raise BadStorValu(name=k,valu=v)

class TufoApi:
    '''
    TufoApi is a mixin class providing get/set APIs around a
    tufo being cached in memory.
    '''

    def __init__(self, core, myfo):
        self.core = core
        self.myfo = myfo

    def get(self, prop):
        '''
        Retrieve a property from the tufo.

        Example:

            foo = tapi.get('foo')

        '''
        form = self.myfo[1].get('tufo:form')
        return self.myfo[1].get('%s:%s' % (form,prop))

    def set(self, prop, valu):
        '''
        Set a property in the tufo ( and persist change to core ).

        Example:

            tapi.set('foo', 20)

        '''
        self.core.setTufoProp(self.myfo, prop, valu)

def firethread(f):
    '''
    A decorator for making a function fire a thread.
    '''
    @functools.wraps(f)
    def callmeth(*args,**kwargs):
        thr = worker(f,*args,**kwargs)
        return thr
    return callmeth

def worker(meth, *args, **kwargs):
    thr = threading.Thread(target=meth,args=args,kwargs=kwargs)
    thr.setDaemon(True)
    thr.start()
    return thr
