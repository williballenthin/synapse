import ast
import traceback
import collections

'''
A synapse cortex is a data storage and indexing abstraction
which is designed to be used as a prop/valu index on various
storage backings.

Most fundamentally, a cortex instance contains rows of:
<id> | <prop> | <valu> | <time>

and is expected to provide indexed access to rows, allow bulk
insertion, and provide for atomic deconfliction if needed.

'''

import synapse.link as s_link
import synapse.telepath as s_telepath

import synapse.cores.ram
import synapse.cores.sqlite
import synapse.cores.postgres

from synapse.eventbus import EventBus

class NoSuchName(Exception):pass
class NoSuchScheme(Exception):pass
class DupCortexName(Exception):pass

corclasses = {
    'tcp':s_telepath.Proxy,

    'ram':synapse.cores.ram.Cortex,
    'sqlite':synapse.cores.sqlite.Cortex,
    'postgres':synapse.cores.postgres.Cortex,
}

def openurl(url):
    '''
    Construct or reference a cortex by url.

    Example:

        core = getCortex('ram://')

    Notes:
        * ram://
        * sqlite3:///<db>[?table=<table>]
        * postgres://[[<passwd>:]<user>@][<host>]/[<db>][?table=<table>]

        * default table name: syncortex

    Todo:
          auditfd=<fd>
          auditfile=<filename>

    '''
    link = s_link.chopLinkUrl(url)
    return openlink(link)

def openlink(link):
    '''
    Open a cortex via a link tuple.
    '''
    cls = corclasses.get(link[0])
    if cls == None:
        raise NoSuchScheme(link[0])
    return cls(link)

def choptag(tag):
    '''
    Chop a tag into hierarchal levels.
    '''
    parts = tag.split('.')
    return [ '.'.join(parts[:x+1]) for x in range(len(parts)) ]

def join2tufo(rows):
    byid = collections.defaultdict(dict)
    [ byid[r[0]].__setitem__( r[1], r[2] ) for r in rows ]
    return list(byid.items())

class MetaCortex(EventBus):

    def __init__(self):
        EventBus.__init__(self)
        self.tagsbyname = {}
        self.coresbyname = {}

        self.coresbytag = collections.defaultdict(list)

        self.onfini( self._onMetaFini )

    def addCortex(self, name, url, tags=()):
        '''
        Tell the MetaCortex about a Cortex instance.

        Example:

            meta.addCortex('woot0','ram:///',tags=('woot.bar',))

        '''
        if self.coresbyname.get(name) != None:
            raise DupCortexName(name)

        core = openurl(url)
        self.coresbyname[name] = core

        alltags = set()

        [ alltags.add(t) for t in choptag(name) ]

        for tag in tags:
            [ alltags.add(t) for t in choptag(tag) ]

        self.tagsbyname[name] = alltags

        for tag in alltags:
            self.coresbytag[tag].append(core)

        return core

    def delCortex(self, name):
        '''
        Remove a given cortex instance by name.

        Example:

            meta.delCortex('woot0')

        '''
        core = self.coresbyname.get(name)
        if core == None:
            raise NoSuchName(name)

        tags = self.tagsbyname.pop(name,())
        for tag in tags:
            self.coresbytag[tag].remove( core )

        core.fini()
        return

    def getCortex(self, name):
        '''
        Return a single Cortex by name ( or None ).

        Example:

            core = meta.getCortex('woot0')
            if core != None:
                stuff(core)

        '''
        return self.coresbyname.get(name)

    def getCortexNames(self):
        '''
        Retrieve a list of cortex names within this metacortex.

        Example:

            names = meta.getCortexNames()

        '''
        return list(self.coresbyname.keys())

    def getCortexes(self, tag):
        '''
        Return a list of cortex instances by tag.

        Example:

            for core in meta.getCortexes('foo.bar'):
                stuff(core)

        '''
        return self.coresbytag.get(tag,())

    def _parseQuery(self, query):
        '''
        Return a parsed dictionary of query info.

        <tag>:<prop>@<mintime>,<maxtime>#<limit>*<by> = <literal>

        '''
        ret = {}
        parts = query.split('=',1)
        if len(parts) == 2:
            ret['valu'] = ast.literal_eval(parts[1])

        parts = parts[0].split('*',1)
        if len(parts) == 2:
            ret['by'] = parts[1]

        parts = parts[0].split('#',1)
        if len(parts) == 2:
            ret['limit'] = int(parts[1],0)

        parts = parts[0].split('@',1)
        if len(parts) == 2:
            timeparts = parts[1].split(',')

        tag,prop = parts[0].split(':',1)

        ret['tag'] = tag.lower()
        ret['prop'] = prop.lower()

        ret['allow'] = True     # hook eventbus to disallow

        return ret

    def getRowsByQuery(self, query):
        '''
        Retrieve rows using a cortex query.

        Example:

            rows = meta.getRowsByQuery('foo:bar=10')

        '''
        qinfo = self._parseQuery(query)
        self.fire('meta:query:rows',query=qinfo)

        if not qinfo.get('allow'):
            return ()

        by = qinfo.pop('by',None)
        tag = qinfo.pop('tag',None)
        prop = qinfo.pop('prop',None)

        valu = qinfo.get('valu')
        limit = qinfo.get('limit')
        mintime = qinfo.get('mintime')
        maxtime = qinfo.get('maxtime')

        cores = self.coresbytag.get(tag)
        if cores == None:
            return ()

        jobs = []
        for core in cores:
            if by != None:
                jid = core.callAsyncApi('getRowsBy',by,prop,valu,limit=limit)
                jobs.append( (core,jid) )
                continue

            if prop == 'id':
                jid = core.callAsyncApi('getRowsById',valu)
                jobs.append( (core,jid) )
                continue

            jid = core.callAsyncApi('getRowsByProp',prop,valu=valu,mintime=mintime,maxtime=maxtime,limit=limit)
            jobs.append( (core,jid) )

        rows = []
        for core,jid in jobs:
            try:
                rows.extend( core.getAsyncReturn(jid) )
            except Exception as e:
                traceback.print_exc()

        return rows

    def getJoinByQuery(self, query):
        '''
        Retrieve a set of rows by cortex query and subsequent join.

        Example:

            rows = meta.getJoinByQuery('foo:bar=10')

        '''
        qinfo = self._parseQuery(query)
        self.fire('meta:query:join',query=qinfo)

        if not qinfo.get('allow'):
            return ()

        by = qinfo.pop('by',None)
        tag = qinfo.pop('tag',None)
        prop = qinfo.pop('prop',None)

        valu = qinfo.get('valu')
        limit = qinfo.get('limit')
        mintime = qinfo.get('mintime')
        maxtime = qinfo.get('maxtime')

        cores = self.coresbytag.get(tag)
        if cores == None:
            return []

        jobs = []
        for core in cores:
            if by != None:
                jid = core.callAsyncApi('getJoinBy',by,prop,valu,limit=limit)
                jobs.append( (core,jid) )
                continue

            if prop == 'id':
                jid = core.callAsyncApi('getJoinById',valu)
                jobs.append( (core,jid) )
                continue

            jid = core.callAsyncApi('getJoinByProp',prop,valu=valu,mintime=mintime,maxtime=maxtime,limit=limit)
            jobs.append( (core,jid) )

        rows = []
        for core,jid in jobs:
            try:
                rows.extend( core.getAsyncReturn(jid) )
            except Exception as e:
                traceback.print_exc()

        return rows

    def getSizeByQuery(self, query):
        '''
        Retrieve the number of rows which match a given cortex query.

        Example:

            count = meta.getSizeByQuery('foo:bar=10')

        '''
        qinfo = self._parseQuery(query)
        self.fire('meta:query:size',query=qinfo)

        if not qinfo.get('allow'):
            return 0

        by = qinfo.pop('by',None)
        tag = qinfo.pop('tag',None)
        prop = qinfo.pop('prop',None)

        valu = qinfo.get('valu')
        limit = qinfo.get('limit')
        mintime = qinfo.get('mintime')
        maxtime = qinfo.get('maxtime')

        cores = self.coresbytag.get(tag)
        if cores == None:
            return 0

        jobs = []
        for core in cores:
            try:
                if by != None:
                    jid = core.callAsyncApi('getSizeBy',by,prop,valu,limit=limit)
                    jobs.append( (core,jid) )
                    continue

                if prop == 'id':
                    jid = core.callAsyncApi('getSizeById',valu)
                    jobs.append( (core,jid) )
                    continue

                jid = core.callAsyncApi('getSizeByProp',prop,valu=valu,mintime=mintime,maxtime=maxtime)
                jobs.append( (core,jid) )

            except Exception as e:
                traceback.print_exc()

        size = 0
        for core,jid in jobs:
            try:
                size += core.getAsyncReturn(jid)
            except Exception as e:
                # FIXME self.fire('exc')
                traceback.print_exc()

        return size

    def getTufosByQuery(self, query):
        '''
        Retrieve a folded set of (ident,info) tuples via join.

        Example:

            tufos = meta.getSizeByQuery('foo:bar=10')

            for tufo in tufos:
                print( tufo[1].get('baz') )

        '''
        rows = self.getJoinByQuery(query)

        return join2tufo(rows)

    def addMetaRows(self, name, rows, async=False):
        '''
        Add the given rows to the specified cortex by name.

        Example:

            meta.addMetaRows('woot',rows)

        '''
        core = self.coresbyname.get(name)
        if core == None:
            raise NoSuchName(name)

        return core.addRows( rows, async=async )

    def callCorApi(self, name, api, *args, **kwargs):
        '''
        Use the MetaCortex to call an API on the named Cortex.

        Example:

            rows = meta.callCorApi('woot','getRowsByProp','hehe',valu=10)

        '''
        core = self.coresbyname.get(name)
        if core == None:
            raise NoSuchName(name)

        # purposely blow up if getattr fails...
        return getattr(core,api)(*args,**kwargs)

    def _onMetaFini(self):

        for core in self.coresbyname.values():
            if isinstance(core,s_telepath.Proxy):
                continue

            core.fini()

