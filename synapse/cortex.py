import os
import logging
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
import synapse.async as s_async
import synapse.telepath as s_telepath

import synapse.lib.sched as s_sched

import synapse.cores.ram
import synapse.cores.sqlite
import synapse.cores.postgres

from synapse.common import *
from synapse.eventbus import EventBus

logger = logging.getLogger(__name__)

class InvalidParam(Exception):
    def __init__(self, name, msg):
        Exception.__init__(self, '%s invalid: %s' % (name,msg))
        self.param = name

corctors = {
    'ram':synapse.cores.ram.initRamCortex,
    'sqlite':synapse.cores.sqlite.Cortex,
    'postgres':synapse.cores.postgres.Cortex,
}

def openurl(url, **opts):
    '''
    Construct or reference a cortex by url.

    Example:

        core = openurl('ram://')

    Notes:
        * ram://
        * sqlite3:///<db>
        * postgres://[[<passwd>:]<user>@][<host>]/[<db>][/<table>]

        * default table name: syncortex

    Todo:
          auditfd=<fd>
          auditfile=<filename>

    '''
    link = s_link.chopLinkUrl(url)

    link[1].update(opts)
    return openlink(link)

def openlink(link):
    '''
    Open a cortex via a link tuple.
    '''
    ctor = corctors.get(link[0])
    if ctor == None:
        return s_telepath.openlink(link)

    return ctor(link)

def choptag(tag):
    '''
    Chop a tag into hierarchal levels.
    '''
    parts = tag.split('.')
    return [ '.'.join(parts[:x+1]) for x in range(len(parts)) ]

if __name__ == '__main__':
    import sys
    import code
    core = openurl(sys.argv[1])
    local = {'core':core,'ask':core.ask,'eval':core.eval}
    code.interact(local=local)
