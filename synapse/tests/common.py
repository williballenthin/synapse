import os
import shutil
import logging
import tempfile
import unittest
import threading
import contextlib

logging.basicConfig(level=logging.WARNING)

import synapse.cortex as s_cortex
import synapse.eventbus as s_eventbus

import synapse.lib.ingest as s_ingest
import synapse.lib.output as s_output
import synapse.lib.thishost as s_thishost

from synapse.common import *

class TooFewEvents(Exception):pass

class TestEnv:

    def __init__(self):
        self.items = {}
        self.tofini = []

    def __getattr__(self, prop):
        item = self.items.get(prop)
        if item == None:
            raise AttributeError(prop)
        return item

    def __enter__(self):
        return self

    def __exit__(self, cls, exc, tb):
        self.fini()

    def add(self, name, item, fini=False):
        self.items[name] = item
        if fini:
            self.tofini.append(item)

    def fini(self):
        for bus in self.tofini:
            bus.fini()


class TestOutPut(s_output.OutPutStr):

    def expect(self, substr):
        outs = str(self)
        if outs.find(substr) == -1:
            raise Exception('TestOutPut.expect(%s) not in %s' % (substr,outs))

class SynTest(unittest.TestCase):

    def getTestWait(self, bus, size, *evts):
        return s_eventbus.Waiter(bus, size, *evts)

    def skipIfNoInternet(self):
        if os.getenv('SYN_TEST_NO_INTERNET'):
            raise unittest.SkipTest('no internet access')

    def getPgCore(self):
        url = os.getenv('SYN_TEST_PG_URL')
        if url != None:
            return s_cortex.openurl(url)

        db = os.getenv('SYN_TEST_PG_DB')
        if db == None:
            raise unittest.SkipTest('no SYN_TEST_PG_DB or SYN_TEST_PG_URL')

        table = 'syn_test_%s' % guid()

        core = s_cortex.openurl('postgres:///%s/%s' % (db,table))

        def droptable():
            with core.getCoreXact() as xact:
                xact.cursor.execute('DROP TABLE %s' % (table,))

        core.onfini(droptable)
        return core

    def getTestOutp(self):
        return TestOutPut()

    def thisHostMust(self, **props):
        for k,v in props.items():
            if s_thishost.get(k) != v:
                raise unittest.SkipTest('skip thishost: %s!=%r' % (k,v))

    def thisHostMustNot(self, **props):
        for k,v in props.items():
            if s_thishost.get(k) == v:
                raise unittest.SkipTest('skip thishost: %s==%r' % (k,v))

    @contextlib.contextmanager
    def getTestDir(self):
        tempdir = tempfile.mkdtemp()
        yield tempdir
        shutil.rmtree(tempdir, ignore_errors=True)

    def eq(self, x, y):
        self.assertEqual(x,y)

    def ne(self, x, y):
        self.assertNotEqual(x,y)

    def true(self, x):
        self.assertTrue(x)

    def false(self, x):
        self.assertFalse(x)

    def nn(self, x):
        self.assertIsNotNone(x)

    def none(self, x):
        self.assertIsNone(x)

    def sorteq(self, x, y):
        return self.eq( sorted(x), sorted(y) )

testdir = os.path.dirname(__file__)
def getTestPath(*paths):
    return os.path.join(testdir,*paths)

def getIngestCore(path, core=None):
    if core == None:
        core = s_cortex.openurl('ram:///')

    gest = s_ingest.loadfile(path)
    with core.getCoreXact() as xact:
        gest.ingest(core)

    return core
