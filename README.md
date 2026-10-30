# arches-abac-permissions

An Attribute Based Access Control (ABAC) framework for Arches resource and nodegroup permissions.

Arches ABAC Permissions extends Arches' default-deny permission framework with **inclusion rules**: a rule describes a set of resource instances by their attributes (for example, the value of a node), and a group assigned to the rule is granted permissions on every resource the rule matches.

## Installation

Arches ABAC Permissions requires Arches 8.2.

### If installing for deployment

The package is not yet published to PyPI. Install it from GitHub:

```bash
pip install "arches-abac-permissions @ git+https://github.com/archesproject/arches-abac-permissions.git@main"
```

To make it a dependency of your project, add the same requirement to the `dependencies` in your project's `pyproject.toml`:

```bash
dependencies = [
    "arches>=8.2.0a13,<8.3.0",
    "arches-abac-permissions @ git+https://github.com/archesproject/arches-abac-permissions.git@main",
]
```

### If installing for development

Clone the repo, then install it into your project's virtual environment in editable mode:

```bash
git clone https://github.com/archesproject/arches-abac-permissions.git
pip install -e arches-abac-permissions --group dev
```

`Important`: Installing arches-abac-permissions installs Arches as a dependency. If you've installed Arches for development using the `--editable` flag, reinstall Arches with the `--editable` flag after installing arches-abac-permissions.

## Project Configuration

1. Add `arches_abac_permissions` to `INSTALLED_APPS` in your project's `settings.py`. List it **after** the core Arches apps (`arches.app.models`, `arches.management`, etc.) and after any other Arches applications, but **before** `arches.app`:

    ```bash
    INSTALLED_APPS = (
        "my_project_name",
        ...
        "arches.app.models",
        "arches.management",
        ...
        "pgtrigger",
        # other arches applications, e.g. "arches_search"
        "arches.extensions.querysets",
        "arches.extensions.vue_components",
        "arches.extensions.controlled_lists",
        "arches_abac_permissions",
    )

    INSTALLED_APPS += (
        "arches",
        "arches.app",
        "django.contrib.admin",
    )
    ```

    Listing it after other Arches applications keeps their templates (for example `index.htm`) taking precedence over the scaffold templates shipped with this package.

2. Set the permission framework, and define `RULE_LOCATIONS`, in `settings.py`:

    ```bash
    PERMISSION_FRAMEWORK = "arches_abac_permission_framework.ArchesAbacPermissionFramework"

    # Required to load inclusion rule classes. The rules directory of every
    # installed Arches application is searched automatically, so this can be
    # empty; add dotted paths here to load rules from other packages.
    RULE_LOCATIONS = []
    ```

    `PERMISSION_FRAMEWORK` is often also set in `settings_local.py`. Check that it isn't overridden there.

3. Run migrations:

    ```bash
    python manage.py migrate
    ```

4. Changing `PERMISSION_FRAMEWORK` requires reindexing:

    ```bash
    python manage.py es reindex_database
    ```

5. Restart your server.

6. Add the rule permissions URLs to your project's `urls.py`, before the Arches core URLs:

    ```python
    urlpatterns = [
        # project-level urls
        path("", include("arches_abac_permissions.api_urls")),
        path("", include("arches.urls")),
    ]
    ```

7. Build the front end so the **Rule Permissions** plugin is bundled. Add the package to your project's `package.json` the same way as other Arches applications, then:

    ```bash
    npm install
    npm run build_development
    ```

## Rule Permissions plugin

Migration `0003` registers a **Rule Permissions** plugin (`/plugins/rule-permissions`). It lets you manage inclusion rules without the Django admin:

-   **Rules** (left): filter, add, and delete rules.
-   **Rule Configuration** (middle): name and description, plus the fields of the rule type: resource model and lifecycle state for _Resource has Lifecycle State_; a resource set for _Resource is in Resource Set_ (only offered when `arches_resource_sets` is installed), a resource model, node and value for _Resource has Node Value_, or a resource model, geometry node and an area drawn on a map (or entered as GeoJSON) for _Resource is in Area_. _Search_ and _QuerySet_ rules are not evaluated yet, so the plugin doesn't offer or list them. More rule types can be added in `arches_abac_permissions/rule_types.py` and `src/arches_abac_permissions/components/RuleConfiguration.vue`. Once a rule is saved, the collapsed **Index SQL** section below its fields shows the SQL for an index that speeds up evaluating it (see [Indexes for rules](#indexes-for-rules)).
-   **Assign Group Permissions to Rule** (right): turn the rule on or off, and grant Read, Update and Delete (`view_`/`change_`/`delete_resourceinstance`) to groups. Groups can be added and deleted here; a group with members cannot be deleted. **Save** stores the rule, its definition and all grants together.

The **Group Membership** view (switch at the top) lists groups, accounts and an editor. Filter accounts by group (or those with no group), open one to add or remove its groups, or tick several and choose **Edit groups** to change them together. Changes apply immediately via `api/abac/users` and `api/abac/users/group_membership`.

Only superusers can see the plugin or call its API (`api/abac/...`). An inactive rule grants nothing.

## How inclusion rules work

An inclusion rule has:

-   a **rule class** (`modulename` + `classname`), which decides how resources are matched;
-   a **definition**, a JSON object of settings specific to the rule class;
-   one or more **group permissions**, each pairing a Django group with the permissions its members get on matching resources.

When Arches checks a user's permissions on a single resource instance (viewing its report, opening it in the editor, deleting it), the framework adds the permissions from every rule that is assigned to one of the user's groups and that matches the resource.

Things to be aware of:

-   **SQL-based search (arches-search) honors inclusion rules; Elasticsearch search does not yet.** Rules apply to single-resource permission checks and to `filter_resource_queryset`, which arches-search uses. Resources a user can access through a rule will not yet appear in core Arches search results or on the search map.
-   **Superusers bypass permission checks**, so rules have no visible effect for them. Test with a non-superuser account.
-   **Users also need the model-level `read_nodegroup` permission** ("Models | node group | Read") to read a resource. Arches requires this in addition to resource-instance permissions.
-   A group permission with no permissions selected grants nothing, and its rule is not evaluated.

### Available rule classes

| `modulename`              | `classname`          | Matches                                                                                                      |
| ------------------------- | -------------------- | ------------------------------------------------------------------------------------------------------------ |
| `lifecycle_state_rule.py` | `LifecycleStateRule` | Resources of a graph that are in a given lifecycle state                                                     |
| `resource_set_rule.py`    | `ResourceSetRule`    | The members of an [arches-resource-sets](https://github.com/archesproject/arches-resource-sets) resource set |
| `tile_node_value_rule.py` | `TileNodeValueRule`  | Resources of a graph with a tile whose node holds a given value                                              |
| `spatial_rule.py`         | `SpatialRule`        | Resources of a graph with a geometry in a given node that intersects an area                                 |
| `search_rule.py`          | `SearchRule`         | Not yet evaluated; stores a saved search query                                                               |
| `queryset_rule.py`        | `QuerySetRule`       | Not yet evaluated                                                                                            |

## Creating a lifecycle state rule

A lifecycle state rule grants permissions on every resource of a given resource model (graph) that is in a given lifecycle state, for example every **Active** resource of the **Person** model. When a resource moves to another lifecycle state, it stops matching the rule.

### 1. Find the graph and lifecycle state ids

The rule needs the id of a resource model and the id of one of the states in that model's resource instance lifecycle. You can list them from the Django shell:

```bash
python manage.py shell
>>> from arches.app.models.models import GraphModel
>>> for graph in GraphModel.objects.filter(isresource=True, source_identifier=None):
...     print(graph.graphid, graph.name)
...     for state in graph.resource_instance_lifecycle.resource_instance_lifecycle_states.all():
...         print("   ", state.id, state.name)
```

Graphs that use Arches' default **Standard** lifecycle share these states:

| State   | Id                                     |
| ------- | -------------------------------------- |
| Draft   | `9375c9a7-dad2-4f14-a5c1-d7e329fdde4f` |
| Active  | `f75bb034-36e3-4ab4-8167-f520cf0b4c58` |
| Retired | `d95d9c0e-0e2c-4450-93a3-d788b91abcc8` |

### 2. Add the rule in the admin

Sign in as a superuser, go to `/admin/`, and under **Arches_Abac_Permissions** choose **Inclusion rules** → **Add inclusion rule**. Enter:

| Field      | Example value             | Notes                              |
| ---------- | ------------------------- | ---------------------------------- |
| Owner      | `select user`             | The user responsible for the rule. |
| Name       | `Active Person resources` | Any descriptive name.              |
| Modulename | `lifecycle_state_rule.py` | Must be exactly this value.        |
| Classname  | `LifecycleStateRule`      | Must be exactly this value.        |
| Definition | see below                 | JSON.                              |

Definition:

```json
{
    "graphid": "22477f01-1a44-11e9-b0a9-000d3ab1e588",
    "lifecycle_state_id": "f75bb034-36e3-4ab4-8167-f520cf0b4c58"
}
```

-   `graphid`: the id of the resource model from step 1. Replace the example value with a graph id from your own project.
-   `lifecycle_state_id`: the id of the lifecycle state from step 1. It must be a state of the graph's lifecycle.

### 3. Grant permissions to a group

On the same page, under **Inclusion rule group permissions**, click **Add another Inclusion rule group permission** and enter:

| Field       | Example value                                  |
| ----------- | ---------------------------------------------- |
| Group       | `Resource Reviewer`                            |
| Permissions | `Models \| resource instance \| Read resource` |

Move each permission you want to grant into the **Chosen permissions** box. The resource-instance permissions are:

| Permission shown in the admin                  | Codename                  | Allows                |
| ---------------------------------------------- | ------------------------- | --------------------- |
| Models \| resource instance \| Read resource   | `view_resourceinstance`   | Viewing the resource  |
| Models \| resource instance \| Update resource | `change_resourceinstance` | Editing the resource  |
| Models \| resource instance \| Delete resource | `delete_resourceinstance` | Deleting the resource |

Click **Save**. To grant the same rule to several groups, add one group permission per group.

### 4. Check the rule

Sign in as a non-superuser member of the group and open a resource of the graph that is in the lifecycle state. You can also check from the Django shell which resources the rule matches:

```bash
python manage.py shell
>>> from arches_abac_permissions.models import InclusionRule
>>> rule = InclusionRule.objects.get(name="Active Person resources")
>>> rule.get_matching_resources()
>>> rule.get_search_rule_url()  # an equivalent Arches search, to view the matches
```

If the rule has no effect, check that:

-   the user is in the group and is not a superuser;
-   the group permission has at least one permission chosen;
-   the user has the `read_nodegroup` permission;
-   `RULE_LOCATIONS` is defined in your settings. If it's missing, loading the rule fails with `AttributeError: 'Settings' object has no attribute 'RULE_LOCATIONS'`;
-   the logs don't show `Inclusion rule ... could not be evaluated`. A rule that can't be evaluated, for example because its graph was deleted, is treated as matching nothing, so it grants nothing but doesn't break other permissions.

## Creating a resource set rule

A resource set rule grants permissions on every member of a resource set from [arches-resource-sets](https://github.com/archesproject/arches-resource-sets). Membership is read when permissions are checked, so adding a resource to the set or removing it takes effect straight away, with no change to the rule.

It needs the optional dependency, and `arches_resource_sets` in `INSTALLED_APPS`:

```bash
pip install "arches-abac-permissions[arches-resource-sets]"
```

Create the rule in the admin as for a lifecycle state rule, with modulename `resource_set_rule.py`, classname `ResourceSetRule` and definition:

```json
{
    "resource_set_id": "<id of the resource set>"
}
```

Things to be aware of:

-   **Deleting the set, or the user who owns it, removes the access silently.** The rule then matches nothing, and nothing is logged.

## Creating a tile node value rule

A tile node value rule grants permissions on every resource of a resource model that has a tile whose node holds a given value, for example every **Person** whose _Classification_ is **Staff**. It reads the `tiles` table directly, so it doesn't need arches-search. Editing the tile changes access straight away.

Create it in the plugin (_Resource has Node Value_) or in the admin with modulename `tile_node_value_rule.py`, classname `TileNodeValueRule` and definition:

```json
{
    "graphid": "<id of the resource model>",
    "nodeid": "<id of a node of that model>",
    "value": "<the value, always as a string>",
    "language": "<language code; string nodes only, empty for any language>"
}
```

| Node datatype                                 | `value`                                 | Matches when                                                               |
| --------------------------------------------- | --------------------------------------- | -------------------------------------------------------------------------- |
| `string`                                      | Text                                    | The text in `language` (or any language) equals `value`                    |
| `non-localized-string`                        | Text                                    | The text equals `value`                                                    |
| `number`                                      | A number, e.g. `"5"` or `"2.5"`         | The number equals `value`                                                  |
| `boolean`                                     | `"true"` or `"false"`                   | The value is the same                                                      |
| `date`                                        | The date as stored, e.g. `"2020-01-31"` | The stored text equals `value`                                             |
| `domain-value`, `domain-value-list`           | The option id                           | The node holds that option                                                 |
| `resource-instance`, `resource-instance-list` | The related resource's id               | The node relates to that resource                                          |
| `reference`                                   | The controlled list item id             | The node holds that list item (needs `arches.extensions.controlled_lists`) |

Things to be aware of:

-   **Matching is exact.** Text is case sensitive and must match the whole value; dates aren't compared as dates.
-   Concept and concept-list nodes, and other datatypes, aren't supported.
-   **Deleting the node or the resource model breaks the rule.** It then matches nothing, and an error is logged each time it's evaluated.

## Creating a spatial rule

A spatial rule grants permissions on every resource of a resource model with a geometry, in a given geometry node, that intersects an area, for example every **Heritage Asset** whose _Location_ is partly inside a district. It reads Arches' `geojson_geometries` table, so editing the geometry changes access straight away.

Create it in the plugin (_Resource is in Area_), where you draw the area on core's `streets` basemap or paste GeoJSON under **Edit as GeoJSON**, or in the admin with modulename `spatial_rule.py`, classname `SpatialRule` and definition:

```json
{
    "graphid": "<id of the resource model>",
    "nodeid": "<id of a geojson-feature-collection node of that model>",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [-0.2, 51.4],
                [0.1, 51.4],
                [0.1, 51.6],
                [-0.2, 51.4]
            ]
        ]
    }
}
```

Things to be aware of:

-   **The area is a GeoJSON `Polygon` or `MultiPolygon` in longitude/latitude (WGS 84).** Any `crs` is ignored. It may have at most 10,000 vertices, and overlapping polygons are merged.
-   A resource matches when any of its geometries in the node touches or overlaps the area.
-   **Deleting the node or the resource model breaks the rule.** It then matches nothing, and an error is logged each time it's evaluated.

## Indexes for rules

Rules are evaluated with SQL whenever permissions are checked, so a large database may need an index for them. The plugin shows the SQL for a saved rule under **Index SQL**, and `InclusionRule.get_index_sql_for_rule()` returns it. Run it against the Arches database with `psql`, outside a transaction (`CREATE INDEX CONCURRENTLY` can't run in one).

-   _Resource has Lifecycle State_: one index on `resource_instances (graphid, resource_instance_lifecycle_state_id)`, shared by every such rule.
-   _Resource is in Resource Set_: none; the set membership table is already indexed.
-   _Resource has Node Value_: a partial GIN index on the node's value in `tiles`, one per node. Rules on the same node share it.
-   _Resource is in Area_: a partial GiST index on `geojson_geometries.geom` for the node, one per node. Rules on the same node share it.

Custom rule classes can return their own SQL from a `get_index_sql(cls, inclusion_rule)` classmethod; the default returns `None`.

## Adding custom rules to your project

You can write your own rule classes in your Arches project; they don't have to live in this package. The examples below use a project called `my_project`.

### How rule classes are found

When a rule is evaluated, its `modulename` and `classname` are looked up with Arches' `get_class_from_modulename`. It searches these packages, in order, and uses the first match:

1. `<app>.rules` and `<app>.pkg.extensions.rules` for every installed app whose `AppConfig` sets `is_arches_application = True`, in `INSTALLED_APPS` order;
2. any packages listed in the `RULE_LOCATIONS` setting.

Arches projects set `is_arches_application = True` in their `AppConfig`, so a rule in `my_project/rules/` is found without any settings changes.

### 1. Write the rule class

Create an empty `my_project/rules/__init__.py`, then add a module for your rule, for example `my_project/rules/my_rule.py`:

```python
from arches_abac_permissions.models import InclusionRule


class MyRule(InclusionRule):
    """Describe what the rule matches and the shape of its definition."""

    @classmethod
    def get_search_rule_url(cls, inclusion_rule):
        # Return a search URL equivalent to the rule, or False if there is none.
        return False

    @classmethod
    def get_matching_resources(cls, inclusion_rule):
        # Return a ResourceInstance queryset of every resource the rule
        # matches. Used to filter querysets, e.g. arches-search results. The
        # rule's settings are in inclusion_rule.definition.
        ...

    @classmethod
    def matches_resource(cls, inclusion_rule, resource):
        # Return True if `resource` matches the rule. Used for
        # single-resource checks; usually
        # cls.get_matching_resources(inclusion_rule).filter(pk=resource.pk).exists()
        ...

    @classmethod
    def validate_definition(cls, inclusion_rule):
        # Raise ValidationError if inclusion_rule.definition is invalid. It is
        # called when the rule is saved in the admin, so mistakes are caught
        # before the rule is used. Optional; the default accepts anything.
        ...

    class Meta:
        proxy = True
        app_label = "my_project"
```

-   Rule classes are **proxy models** of `InclusionRule`, so they share its table and add no columns.
-   Set `app_label` to your project's app label, or leave it out. **Don't copy `app_label = "arches_abac_permissions"`** from the built-in rules: if you do, `makemigrations` will try to write your rule's migration into this package.
-   **Give the module a name the built-in rules don't use** (not `lifecycle_state_rule`, `resource_set_rule`, `tile_node_value_rule`, `spatial_rule`, `search_rule` or `queryset_rule`). Lookup uses the first match in `INSTALLED_APPS` order, so a duplicate name could load the wrong class.

See `arches_abac_permissions/rules/lifecycle_state_rule.py` for a complete example.

### 2. Register the rule when Django starts

Import the module in your project's `AppConfig.ready()` so Django registers the proxy model at startup. Without this, `makemigrations` and content types won't know about the model until a rule using it is evaluated.

```python
from django.apps import AppConfig


class MyProjectConfig(AppConfig):
    name = "my_project"
    is_arches_application = True

    def ready(self):
        # Register proxy rule models so they are known to the app registry.
        from my_project.rules import my_rule  # noqa
```

### 3. Create the migration

```bash
python manage.py makemigrations my_project
python manage.py migrate
```

The migration only records the proxy model and creates no table.

### 4. Use the rule

Create an inclusion rule in the admin as described in [Creating a lifecycle state rule](#creating-a-lifecycle-state-rule), entering your own module and class:

| Field      | Value                                 |
| ---------- | ------------------------------------- |
| Modulename | `my_rule.py`                          |
| Classname  | `MyRule`                              |
| Definition | whatever JSON your rule class expects |

## Running tests

```bash
python manage.py test tests --settings="tests.test_settings"
```
