import uuid
from unittest import skipUnless

from django.apps import apps
from django.core.exceptions import ValidationError
from django.urls import reverse

from arches.app.models.models import Language, Node, NodeGroup, TileModel
from arches_abac_permissions.rules.tile_node_value_rule import TileNodeValueRule
from tests.test_inclusion_rules import make_rule
from tests.test_views import ApiTestCase

CONTROLLED_LISTS_INSTALLED = apps.is_installed("arches.extensions.controlled_lists")


class TileNodeValueTestCase(ApiTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for code, name in (("en", "English"), ("es", "Spanish")):
            Language.objects.get_or_create(code=code, defaults={"name": name})
        cls.value_nodegroup = NodeGroup.objects.create()
        cls.option_id = str(uuid.uuid4())
        cls.nodes = {
            datatype: Node.objects.create(
                name=datatype,
                alias=datatype.replace("-", "_"),
                datatype=datatype,
                graph=cls.graph,
                nodegroup=cls.value_nodegroup,
                istopnode=False,
                config=config,
            )
            for datatype, config in (
                ("string", {}),
                ("non-localized-string", {}),
                ("number", {}),
                ("boolean", {"trueLabel": "Yes", "falseLabel": "No"}),
                ("date", {"dateFormat": "YYYY-MM-DD"}),
                ("domain-value", {"options": [{"id": cls.option_id, "text": "A"}]}),
                (
                    "domain-value-list",
                    {"options": [{"id": cls.option_id, "text": {"en": "A"}}]},
                ),
                ("resource-instance", {}),
                ("resource-instance-list", {}),
                ("geojson-feature-collection", {}),
            )
        }
        cls.related = cls.make_resource(cls.graph, cls.active_state)
        cls.hit = cls.make_resource(cls.graph, cls.active_state)
        cls.miss = cls.make_resource(cls.graph, cls.active_state)
        cls.set_values(
            cls.hit,
            {
                "string": {"es": {"value": "hola", "direction": "ltr"}},
                "non-localized-string": "abc",
                "number": 5.0,
                "boolean": True,
                "date": "2020-01-31",
                "domain-value": cls.option_id,
                "domain-value-list": [str(uuid.uuid4()), cls.option_id],
                "resource-instance": [{"resourceId": str(cls.related.pk)}],
                "resource-instance-list": [
                    {"resourceId": str(uuid.uuid4())},
                    {"resourceId": str(cls.related.pk)},
                ],
            },
        )
        cls.set_values(
            cls.miss,
            {
                "string": {"en": {"value": "hola!", "direction": "ltr"}},
                "non-localized-string": "abcd",
                "number": 6,
                "boolean": False,
                "date": "2020-01-30",
                "domain-value": str(uuid.uuid4()),
                "domain-value-list": [],
                "resource-instance": None,
                "resource-instance-list": [{"resourceId": str(uuid.uuid4())}],
            },
        )

    @classmethod
    def set_values(cls, resource, values):
        TileModel.objects.create(
            resourceinstance=resource,
            nodegroup=cls.value_nodegroup,
            data={str(cls.nodes[dt].pk): value for dt, value in values.items()},
            sortorder=0,
        )

    def definition(self, datatype, value, **extra):
        node = self.nodes.get(datatype)
        return {
            "graphid": str(self.graph.pk),
            "nodeid": str(node.pk) if node else str(uuid.uuid4()),
            "value": value,
            **extra,
        }

    def make_value_rule(self, datatype, value, **extra):
        return make_rule(
            modulename="tile_node_value_rule.py",
            classname="TileNodeValueRule",
            definition=self.definition(datatype, value, **extra),
        )


class TileNodeValueRuleTests(TileNodeValueTestCase):
    def assertMatchesOnlyHit(self, rule):
        self.assertEqual(set(rule.get_matching_resources()), {self.hit})
        self.assertTrue(rule.matches_resource(self.hit))
        self.assertFalse(rule.matches_resource(self.miss))
        self.assertFalse(rule.matches_resource(self.related))

    def test_matches_each_datatype(self):
        related = str(self.related.pk)
        for datatype, value, extra in (
            ("string", "hola", {"language": "es"}),
            ("non-localized-string", "abc", {}),
            ("number", "5", {}),
            ("boolean", "true", {}),
            ("date", "2020-01-31", {}),
            ("domain-value", self.option_id, {}),
            ("domain-value-list", self.option_id, {}),
            ("resource-instance", related, {}),
            ("resource-instance-list", related.upper(), {}),
        ):
            with self.subTest(datatype=datatype):
                rule = self.make_value_rule(datatype, value, **extra)
                rule.full_clean()
                self.assertMatchesOnlyHit(rule)

    def test_string_language(self):
        self.assertMatchesOnlyHit(self.make_value_rule("string", "hola"))
        rule = self.make_value_rule("string", "hola", language="en")
        self.assertEqual(set(rule.get_matching_resources()), set())

    def test_boolean_false(self):
        rule = self.make_value_rule("boolean", "false")
        self.assertEqual(set(rule.get_matching_resources()), {self.miss})

    def test_other_graph_does_not_match(self):
        rule = self.make_value_rule("non-localized-string", "abc")
        self.assertFalse(rule.matches_resource(self.other_graph_active))

    def test_invalid_definitions(self):
        for definition in (
            {},
            self.definition("number", ""),
            self.definition("missing-node", "x"),
            {**self.definition("number", "5"), "graphid": str(self.branch.pk)},
            {**self.definition("number", "5"), "graphid": str(self.other_graph.pk)},
            self.definition("geojson-feature-collection", "x"),
            self.definition("number", "five"),
            self.definition("number", "NaN"),
            self.definition("boolean", "yes"),
            self.definition("non-localized-string", "x", language="en"),
            self.definition("string", "x", language="xx-not-a-language"),
            self.definition("domain-value", str(uuid.uuid4())),
            self.definition("resource-instance", "not-a-uuid"),
            self.definition("resource-instance", str(uuid.uuid4())),
        ):
            with self.subTest(definition=definition):
                rule = make_rule(
                    modulename="tile_node_value_rule.py",
                    classname="TileNodeValueRule",
                    definition=definition,
                )
                with self.assertRaises(ValidationError):
                    rule.full_clean()

    def test_index_sql(self):
        node = self.nodes["number"]
        sql = self.make_value_rule("number", "5").get_index_sql_for_rule()
        self.assertIn(f"abac_tile_node_{node.pk.hex}", sql)
        self.assertIn(f"(tiledata -> '{node.pk}') jsonb_path_ops", sql)
        self.assertIn(f"WHERE nodegroupid = '{self.value_nodegroup.pk}'", sql)

    @skipUnless(CONTROLLED_LISTS_INSTALLED, "controlled lists not installed")
    def test_reference(self):
        from arches.extensions.controlled_lists.models import List, ListItem

        controlled_list = List.objects.create(name="Colors")
        item = ListItem.objects.create(
            list=controlled_list, sortorder=0, uri="http://example.com/red"
        )
        node = Node.objects.create(
            name="reference",
            alias="reference",
            datatype="reference",
            graph=self.graph,
            nodegroup=self.value_nodegroup,
            istopnode=False,
            config={"controlledList": str(controlled_list.pk), "multiValue": True},
        )
        TileModel.objects.filter(resourceinstance=self.hit).update(
            data={
                str(node.pk): [
                    {
                        "uri": item.uri,
                        "list_id": str(controlled_list.pk),
                        "labels": [{"list_item_id": str(item.pk), "value": "Red"}],
                    }
                ]
            }
        )
        self.nodes["reference"] = node
        rule = self.make_value_rule("reference", str(item.pk))
        rule.full_clean()
        self.assertEqual(set(rule.get_matching_resources()), {self.hit})

        other = self.make_value_rule("reference", str(uuid.uuid4()))
        with self.assertRaises(ValidationError):
            other.full_clean()


class TileNodeValueApiTests(TileNodeValueTestCase):
    def test_create_through_api(self):
        definition = self.definition("number", "5")
        created = self.create_rule(rule_type="tile_node_value", definition=definition)
        self.assertEqual(created["rule_type"], "tile_node_value")
        self.assertEqual(created["definition"], definition)
        self.assertIn("CREATE INDEX CONCURRENTLY", created["index_sql"])

    def test_invalid_value_rejected(self):
        response = self.send(
            "post",
            reverse("abac_rules"),
            self.payload(
                rule_type="tile_node_value",
                definition=self.definition("number", "five"),
            ),
        )
        self.assertEqual(response.status_code, 400)

    def test_index_sql_for_other_rule_types(self):
        self.assertIn("resource_instances", self.create_rule()["index_sql"])

    def test_nodes(self):
        url = reverse("abac_resource_model_nodes", args=[self.graph.pk])
        nodes = {
            node["datatype"]: node for node in self.client.get(url).json()["nodes"]
        }
        self.assertNotIn("geojson-feature-collection", nodes)
        self.assertEqual(
            nodes["domain-value"]["options"], [{"id": self.option_id, "label": "A"}]
        )
        self.assertEqual(
            nodes["domain-value-list"]["options"],
            [{"id": self.option_id, "label": "A"}],
        )
        self.assertEqual(nodes["boolean"]["true_label"], "Yes")
        self.assertEqual(nodes["date"]["date_format"], "YYYY-MM-DD")

    def test_languages(self):
        languages = self.client.get(reverse("abac_languages")).json()["languages"]
        self.assertTrue({"en", "es"} <= {language["code"] for language in languages})

    @skipUnless(CONTROLLED_LISTS_INSTALLED, "controlled lists not installed")
    def test_controlled_list_items(self):
        from arches.extensions.controlled_lists.models import List, ListItem

        controlled_list = List.objects.create(name="Colors")
        parent = ListItem.objects.create(
            list=controlled_list, sortorder=1, uri="http://example.com/warm"
        )
        ListItem.objects.create(
            list=controlled_list,
            parent=parent,
            sortorder=0,
            uri="http://example.com/red",
        )
        ListItem.objects.create(
            list=controlled_list, sortorder=0, uri="http://example.com/blue"
        )
        url = reverse("abac_controlled_list_items", args=[controlled_list.pk])
        items = self.client.get(url).json()["items"]
        self.assertEqual(
            [(item["label"], item["depth"]) for item in items],
            [
                ("http://example.com/blue", 0),
                ("http://example.com/warm", 0),
                ("http://example.com/red", 1),
            ],
        )
