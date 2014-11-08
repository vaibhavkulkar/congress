# Copyright (c) 2013 VMware, Inc. All rights reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

import unittest

import congress.dse.d6cage
import congress.policy.compile as compile
import congress.policy.runtime as runtime
import congress.tests.helper as helper


class TestDSE(unittest.TestCase):

    def test_cage(self):
        """Test basic DSE functionality."""
        cage = congress.dse.d6cage.d6Cage()
        cage.loadModule("TestDriver",
                        helper.data_module_path("test_driver.py"))
        args = helper.datasource_openstack_args()
        args['poll_time'] = 0
        cage.createservice(name="test1", moduleName="TestDriver", args=args)
        cage.createservice(name="test2", moduleName="TestDriver", args=args)
        test1 = cage.service_object('test1')
        test2 = cage.service_object('test2')
        test1.subscribe('test2', 'p', callback=test1.receive_msg)
        test2.publish('p', 42)
        helper.retry_check_for_message_to_arrive(test1)
        self.assertTrue(test1.msg.body, 42)

    def test_policy(self):
        """Test basic DSE functionality with policy engine."""
        cage = congress.dse.d6cage.d6Cage()
        cage.loadModule("TestDriver",
                        helper.data_module_path("test_driver.py"))
        cage.loadModule("TestPolicy", helper.policy_module_path())
        cage.createservice(name="data", moduleName="TestDriver",
                           args=helper.datasource_openstack_args())
        cage.createservice(name="policy", moduleName="TestPolicy",
                           args={'d6cage': cage, 'rootdir': ''})
        data = cage.services['data']['object']
        policy = cage.services['policy']['object']
        policy.subscribe('data', 'p', callback=policy.receive_msg)
        data.publish('p', 42)
        helper.retry_check_for_message_to_arrive(policy)
        self.assertTrue(policy.msg.body, 42)

    def test_policy_data(self):
        """Test policy properly inserts data and processes it normally."""
        cage = congress.dse.d6cage.d6Cage()
        cage.loadModule("TestDriver",
                        helper.data_module_path("test_driver.py"))
        cage.loadModule("TestPolicy", helper.policy_module_path())
        cage.createservice(name="data", moduleName="TestDriver",
                           args=helper.datasource_openstack_args())
        cage.createservice(name="policy", moduleName="TestPolicy",
                           args={'d6cage': cage, 'rootdir': ''})
        data = cage.services['data']['object']
        policy = cage.services['policy']['object']
        # turn off module-schema syntax checking
        policy.create_policy('data')
        policy.set_schema('data', compile.Schema({'p': (1,)}))
        policy.subscribe('data', 'p', callback=policy.receive_data)
        formula = compile.parse1('p(1)')
        # sending a single Insert.  (Default for Event is Insert.)
        data.publish('p', [runtime.Event(formula)])
        helper.retry_check_db_equal(policy, 'data:p(x)', 'data:p(1)')

    def test_policy_tables(self):
        """Test basic DSE functionality with policy engine and the API."""
        cage = congress.dse.d6cage.d6Cage()
        cage.loadModule("TestDriver",
                        helper.data_module_path("test_driver.py"))
        cage.loadModule("TestPolicy", helper.policy_module_path())
        cage.createservice(name="data", moduleName="TestDriver",
                           args=helper.datasource_openstack_args())
        # using regular testdriver as API for now
        cage.createservice(name="api", moduleName="TestDriver",
                           args=helper.datasource_openstack_args())
        cage.createservice(name="policy", moduleName="TestPolicy",
                           args={'d6cage': cage, 'rootdir': ''})
        data = cage.services['data']['object']
        api = cage.services['api']['object']
        policy = cage.services['policy']['object']
        policy.create_policy('data')
        policy.set_schema('data', compile.Schema({'q': (1,)}))
        policy.subscribe('api', 'policy-update',
                         callback=policy.receive_policy_update)
        # simulate API call for insertion of policy statements
        formula = compile.parse1('p(x) :- data:q(x)')
        api.publish('policy-update', [runtime.Event(formula)])
        helper.retry_check_nonempty_last_policy_change(policy)
        # simulate data source publishing to q
        formula = compile.parse1('q(1)')
        data.publish('q', [runtime.Event(formula)])
        helper.retry_check_db_equal(policy, 'data:q(x)', 'data:q(1)')
        # check that policy did the right thing with data
        e = helper.db_equal(policy.select('p(x)'), 'p(1)')
        self.assertTrue(e, 'Policy insert')
        # check that publishing into 'p' does not work
        formula = compile.parse1('p(3)')
        data.publish('p', [runtime.Event(formula)])
        # can't actually check that the update for p does not arrive
        # so instead wait a bit and check
        helper.pause()
        e = helper.db_equal(policy.select('p(x)'), 'p(1)')
        self.assertTrue(e, 'Policy non-insert')
