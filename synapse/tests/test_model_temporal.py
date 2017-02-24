import synapse.cortex as s_cortex

from synapse.tests.common import *

class InetModelTest(SynTest):

    def test_model_time_minmax(self):
        with s_cortex.openurl('ram:///') as core:
            core.addType('foo:min',subof='time',ismin=1)
            core.addType('foo:max',subof='time',ismax=1)
            core.addTufoForm('foo', ptype='str')
            core.addTufoProp('foo', 'earliest', ptype='foo:min')
            core.addTufoProp('foo', 'latest', ptype='foo:max')

            tufo = core.formTufoByFrob('foo', 'a', **{'earliest':10, 'latest':10})
            self.eq(tufo[1]['foo:earliest'], 10)
            self.eq(tufo[1]['foo:latest'], 10)

            core.setTufoProp(tufo, 'earliest', 100)
            self.eq(tufo[1]['foo:earliest'], 10)
            core.setTufoProp(tufo, 'earliest', 1)
            self.eq(tufo[1]['foo:earliest'], 1)

            core.setTufoProp(tufo, 'latest', 100)
            self.eq(tufo[1]['foo:latest'], 100)
            core.setTufoProp(tufo, 'latest', 1)
            self.eq(tufo[1]['foo:latest'], 100)
