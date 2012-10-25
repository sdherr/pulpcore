# -*- coding: utf-8 -*-
# Copyright (c) 2012 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

import mock
from pymongo.objectid import ObjectId

from base_db_upgrade import BaseDbUpgradeTests
from pulp.server.upgrade.model import UpgradeStepReport
from pulp.server.upgrade.db import repos


class ReposUpgradeNoFilesTests(BaseDbUpgradeTests):

    def setUp(self):
        super(ReposUpgradeNoFilesTests, self).setUp()
        repos.SKIP_LOCAL_FILES = True

    def tearDown(self):
        super(ReposUpgradeNoFilesTests, self).tearDown()
        repos.SKIP_LOCAL_FILES = False

    def test_repos(self):
        # Test
        report = repos.upgrade(self.v1_test_db.database, self.tmp_test_db.database)

        # Verify
        self.assertTrue(isinstance(report, UpgradeStepReport))
        self.assertTrue(report.success)

        self.assertTrue(self.v1_test_db.database.repos.count() > 0)
        v1_repos = self.v1_test_db.database.repos.find()
        for v1_repo in v1_repos:
            repo_id = v1_repo['id']

            # Repo
            v2_repo = self.tmp_test_db.database.repos.find_one({'id' : repo_id})
            self.assertTrue(v2_repo is not None)
            self.assertTrue(isinstance(v2_repo['_id'], ObjectId))
            self.assertEqual(v2_repo['id'], v1_repo['id'])
            self.assertEqual(v2_repo['display_name'], v1_repo['name'])
            self.assertEqual(v2_repo['description'], None)
            self.assertEqual(v2_repo['scratchpad'], {})
            self.assertEqual(v2_repo['content_unit_count'], 0)

            # Importer
            v2_importer = self.tmp_test_db.database.repo_importers.find_one({'repo_id' : repo_id})
            self.assertTrue(v2_importer is not None)
            self.assertTrue(isinstance(v2_importer['_id'], ObjectId))
            self.assertEqual(v2_importer['id'], repos.YUM_IMPORTER_ID)
            self.assertEqual(v2_importer['importer_type_id'], repos.YUM_IMPORTER_TYPE_ID)
            self.assertEqual(v2_importer['last_sync'], v1_repo['last_sync'])

            config = v2_importer['config']
            self.assertEqual(config['feed'], v1_repo['source']['url'])
            self.assertEqual(config['ssl_ca_cert'], v1_repo['feed_ca'])
            self.assertEqual(config['ssl_client_cert'], v1_repo['feed_cert'])
            self.assertTrue('skip' not in config)
            self.assertTrue('proxy_url' not in config)
            self.assertTrue('proxy_port' not in config)
            self.assertTrue('proxy_user' not in config)
            self.assertTrue('proxy_pass' not in config)

            # Distributor
            v2_distributor = self.tmp_test_db.database.repo_distributors.find_one({'repo_id' : repo_id})
            self.assertTrue(v2_distributor is not None)
            self.assertTrue(isinstance(v2_distributor['_id'], ObjectId))
            self.assertEqual(v2_distributor['id'], repos.YUM_DISTRIBUTOR_ID)
            self.assertEqual(v2_distributor['distributor_type_id'], repos.YUM_DISTRIBUTOR_TYPE_ID)
            self.assertEqual(v2_distributor['auto_publish'], True)
            self.assertEqual(v2_distributor['scratchpad'], None)
            self.assertEqual(v2_distributor['last_publish'], v1_repo['last_sync'])

            config = v2_distributor['config']
            self.assertEqual(config['relative_url'], v1_repo['relative_path'])
            self.assertEqual(config['http'], False)
            self.assertEqual(config['https'], True)
            self.assertTrue('https_ca' not in config)
            self.assertTrue('gpgkey' not in config)

    @mock.patch('pulp.server.upgrade.db.repos._repos')
    def test_repos_failed_repo_step(self, mock_repos_call):
        # Setup
        mock_repos_call.return_value = False

        # Test
        report = repos.upgrade(self.v1_test_db.database, self.tmp_test_db.database)

        # Verify
        self.assertTrue(not report.success)

    @mock.patch('pulp.server.upgrade.db.repos._repo_importers')
    def test_repos_failed_importer_step(self, mock_importer_call):
        # Setup
        mock_importer_call.return_value = False

        # Test
        report = repos.upgrade(self.v1_test_db.database, self.tmp_test_db.database)

        # Verify
        self.assertTrue(not report.success)

    @mock.patch('pulp.server.upgrade.db.repos._repo_distributors')
    def test_repos_failed_distributor_step(self, mock_distributor_call):
        # Setup
        mock_distributor_call.return_value = False

        # Test
        report = repos.upgrade(self.v1_test_db.database, self.tmp_test_db.database)

        # Verify
        self.assertTrue(not report.success)


class RepoUpgradeWithFilesTests(BaseDbUpgradeTests):
    pass


class RepoUpgradeGroupsTests(BaseDbUpgradeTests):

    def setUp(self):
        super(RepoUpgradeGroupsTests, self).setUp()

        # Unfortunately the test database doesn't have any repo groups, so only
        # for these tests we'll munge the DB for interesting data.

        self.num_repos = 10
        self.num_groups = 3

        new_repos = []
        self.repo_ids_by_group_id = {}
        for i in range(0, self.num_repos):
            repo_id = 'repo-%s' % i
            group_id = 'group-%s' % (i % self.num_groups)
            new_repo = {
                'id' : repo_id,
                'groupid' : [group_id],
                'relative_path' : 'path-%s' % i,
            }
            self.repo_ids_by_group_id.setdefault(group_id, []).append(repo_id)

            if i % 2 == 0:
                new_repo['groupid'].append('group-x')
                self.repo_ids_by_group_id.setdefault('group-x', []).append(repo_id)

            new_repos.append(new_repo)

        self.v1_test_db.database.repos.insert(new_repos, safe=True)

    def test_repo_groups(self):
        # Test
        report = UpgradeStepReport()
        result = repos._repo_groups(self.v1_test_db.database, self.tmp_test_db.database, report)

        # Verify
        self.assertEqual(result, True)

        v2_coll = self.tmp_test_db.database.repo_groups
        all_groups = list(v2_coll.find())
        self.assertEqual(self.num_groups + 1, len(all_groups))

        for group_id, repo_ids in self.repo_ids_by_group_id.items():
            group = self.tmp_test_db.database.repo_groups.find_one({'id' : group_id})
            self.assertTrue(isinstance(group['_id'], ObjectId))
            self.assertEqual(group['id'], group_id)
            self.assertEqual(group['display_name'], None)
            self.assertEqual(group['description'], None)
            self.assertEqual(group['notes'], {})
            self.assertEqual(group['repo_ids'], repo_ids)

