import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('site_release', root/'deploy/release.py')
release = importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
spec = importlib.util.spec_from_file_location('site_runtime', root/'config/runtime_env.py')
loader = importlib.util.module_from_spec(spec);spec.loader.exec_module(loader)


class SiteReleaseTests(unittest.TestCase):
    def config(self):
        return {'SECRET_KEY':'synthetic','DB_NAME':'synthetic','DB_USER':'postgres','DB_PASSWORD':'synthetic',
                'DB_HOST':'postgres','DB_PORT':'5432','ALLOWED_HOSTS':'site.arnatech.id','REDIS_URL':'redis://redis/1',
                'ARNA_SSO_BASE_URL':'https://sso.arnatech.id/api','DEBUG':'false'}

    def test_incomplete_or_changed_database_binding_is_rejected(self):
        for values in ({'DB_HOST':'new'}, {**self.config(),'DB_PASSWORD':'new'}, {**self.config(),'DEBUG':'true'}):
            with self.assertRaises(RuntimeError):release.validate_configuration(values,self.config())

    def test_full_runtime_is_mounted_and_public_key_is_release_scoped(self):
        values=release.validate_configuration(self.config(),self.config())
        self.assertEqual(values['SSO_JWT_PUBLIC_KEY_PATH'],'/run/secrets/site_sso_public')
        args=release.secret_update_args({'Env':['DB_PASSWORD=synthetic']},{'secrets':{'runtime':'runtime-id','public':'public-id'}})
        self.assertNotIn('synthetic',' '.join(args))
        self.assertIn('SITE_RUNTIME_SECRET_PATH=/run/secrets/site_runtime',args)

    def test_no_rollout_without_completed_migrations(self):
        with patch.object(release,'artifact',return_value={'migration':'failed'}),patch.object(release,'run') as command:
            with self.assertRaises(RuntimeError):release.roll('a'*40,Path('/synthetic'))
            command.assert_not_called()

    def test_failed_one_off_task_stops_the_gate(self):
        with patch.object(release,'run',side_effect=['task-id',json.dumps([{'ID':'task-id','Status':{'State':'failed','ContainerStatus':{'ExitCode':1}}}])]):
            with self.assertRaises(RuntimeError):release.wait_task('synthetic',seconds=1)

    def test_runtime_secret_is_complete_and_loaded_before_settings(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'runtime.json';path.write_text(json.dumps({'DB_HOST':'new','EXTRA':'preserved'}))
            with patch.dict(os.environ,{'SITE_RUNTIME_SECRET_PATH':str(path),'DB_HOST':'old'}):
                loader.load_runtime_env();self.assertEqual(os.environ['DB_HOST'],'new')
                self.assertEqual(os.environ['EXTRA'],'preserved')

    def test_wrong_repository_or_mutable_tag_cannot_be_deployed(self):
        self.assertTrue(release.digest_valid('arnatechid/arna_site@sha256:'+'a'*64))
        self.assertFalse(release.digest_valid('arnatechid/arna_site:latest'))
        self.assertFalse(release.digest_valid('ardzix/file_manager@sha256:'+'a'*64))
