"""Real ORM isolation checks with an isolated in-memory reference table."""
import copy
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connections
from rest_framework.exceptions import ValidationError

from storage.models import MediaReference
from storage.views import MediaReferenceViewSet


class SharedMediaIsolationTests(unittest.TestCase):
    alias = 'media_isolation'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config = copy.deepcopy(connections.databases['default'])
        config.update(ENGINE='django.db.backends.sqlite3', NAME=':memory:', OPTIONS={}, CONN_MAX_AGE=0)
        connections.databases[cls.alias] = config
        cls.db = connections[cls.alias]
        with cls.db.schema_editor() as editor:
            editor.create_model(MediaReference)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        del connections[cls.alias]
        connections.databases.pop(cls.alias, None)
        super().tearDownClass()

    def setUp(self):
        MediaReference.objects.using(self.alias).all().delete()
        self.a, self.b = uuid.uuid4(), uuid.uuid4()
        self.rows = []
        for tenant in (self.a, self.b, None):
            self.rows.append(MediaReference.objects.using(self.alias).create(
                tenant_id=tenant, file_id=uuid.uuid4(), url='https://storage.arnatech.id/synthetic',
                display_name='synthetic', status='active'))

    def view(self, tenant_id, **extra):
        view = MediaReferenceViewSet()
        view.queryset = MediaReference.objects.using(self.alias).all()
        view.request = SimpleNamespace(tenant=SimpleNamespace(public_id=tenant_id,
            **{'tenancy_mode': 'shared', 'schema_name': 'pool_shared', **extra}))
        return view

    def test_shared_pool_lists_only_the_selected_tenant_and_hides_legacy_unknown_owner(self):
        self.assertEqual(list(self.view(self.a).get_queryset()), [self.rows[0]])
        self.assertEqual(list(self.view(self.b).get_queryset()), [self.rows[1]])

    def test_foreign_reference_cannot_be_retrieved_or_resolved_as_a_local_reference(self):
        view = self.view(self.b)
        with self.assertRaises(MediaReference.DoesNotExist):
            view.get_queryset().get(pk=self.rows[0].pk)
        identifier, reference = view._resolve_file_id(self.rows[0].pk)
        self.assertIsNone(reference)
        self.assertEqual(identifier, str(self.rows[0].pk))

    def test_missing_tenant_returns_no_media(self):
        self.assertEqual(list(self.view(None).get_queryset()), [])

    def test_legacy_null_records_are_allowed_only_in_a_single_tenant_dedicated_schema(self):
        view = self.view(self.a, tenancy_mode='dedicated', schema_name='dedicated_test')
        with patch('core.models.Tenant.objects.filter') as query:
            query.return_value.count.return_value = 1
            self.assertEqual(set(view.get_queryset().values_list('id', flat=True)), {self.rows[0].pk, self.rows[2].pk})
            query.return_value.count.return_value = 2
            self.assertEqual(list(view.get_queryset()), [self.rows[0]])

    def test_raw_create_cannot_create_unverified_or_unowned_references(self):
        serializer = Mock()
        with self.assertRaises(ValidationError):
            self.view(self.a).perform_create(serializer)
        serializer.save.assert_not_called()
