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

The package has no URLs or front-end assets of its own, so no changes are needed to `urls.py` or `package.json`.

## How inclusion rules work

An inclusion rule has:

- a **rule class** (`modulename` + `classname`), which decides how resources are matched;
- a **definition**, a JSON object of settings specific to the rule class;
- one or more **group permissions**, each pairing a Django group with the permissions its members get on matching resources.

When Arches checks a user's permissions on a single resource instance (viewing its report, opening it in the editor, deleting it), the framework adds the permissions from every rule that is assigned to one of the user's groups and that matches the resource.

Things to be aware of:

- **SQL-based search (arches-search) honors inclusion rules; Elasticsearch search does not yet.** Rules apply to single-resource permission checks and to `filter_resource_queryset`, which arches-search uses. Resources a user can access through a rule will not yet appear in core Arches search results or on the search map.
- **Superusers bypass permission checks**, so rules have no visible effect for them. Test with a non-superuser account.
- **Users also need the model-level `read_nodegroup` permission** ("Models | node group | Read") to read a resource. Arches requires this in addition to resource-instance permissions.
- A group permission with no permissions selected grants nothing, and its rule is not evaluated.

### Available rule classes

| `modulename` | `classname` | Matches |
|---|---|---|
| `lifecycle_state_rule.py` | `LifecycleStateRule` | Resources of a graph that are in a given lifecycle state |
| `search_rule.py` | `SearchRule` | Not yet evaluated; stores a saved search query |
| `queryset_rule.py` | `QuerySetRule` | Not yet evaluated |

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

| State | Id |
|---|---|
| Draft | `9375c9a7-dad2-4f14-a5c1-d7e329fdde4f` |
| Active | `f75bb034-36e3-4ab4-8167-f520cf0b4c58` |
| Retired | `d95d9c0e-0e2c-4450-93a3-d788b91abcc8` |

### 2. Add the rule in the admin

Sign in as a superuser, go to `/admin/`, and under **Arches_Abac_Permissions** choose **Inclusion rules** → **Add inclusion rule**. Enter:

| Field | Example value | Notes |
|---|---|---|
| Owner | *(leave blank)* | Optional. The user responsible for the rule. |
| Name | `Active Person resources` | Any descriptive name. |
| Modulename | `lifecycle_state_rule.py` | Must be exactly this value. |
| Classname | `LifecycleStateRule` | Must be exactly this value. |
| Definition | see below | JSON. |

Definition:

```json
{
    "graphid": "22477f01-1a44-11e9-b0a9-000d3ab1e588",
    "lifecycle_state_id": "f75bb034-36e3-4ab4-8167-f520cf0b4c58"
}
```

- `graphid`: the id of the resource model from step 1. Replace the example value with a graph id from your own project.
- `lifecycle_state_id`: the id of the lifecycle state from step 1. It must be a state of the graph's lifecycle.

### 3. Grant permissions to a group

On the same page, under **Inclusion rule group permissions**, click **Add another Inclusion rule group permission** and enter:

| Field | Example value |
|---|---|
| Group | `Resource Reviewer` |
| Permissions | `Models \| resource instance \| Read resource` |

Move each permission you want to grant into the **Chosen permissions** box. The resource-instance permissions are:

| Permission shown in the admin | Codename | Allows |
|---|---|---|
| Models \| resource instance \| Read resource | `view_resourceinstance` | Viewing the resource |
| Models \| resource instance \| Update resource | `change_resourceinstance` | Editing the resource |
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

- the user is in the group and is not a superuser;
- the group permission has at least one permission chosen;
- the user has the `read_nodegroup` permission;
- `RULE_LOCATIONS` is defined in your settings. If it's missing, loading the rule fails with `AttributeError: 'Settings' object has no attribute 'RULE_LOCATIONS'`.

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

    class Meta:
        proxy = True
        app_label = "my_project"
```

- Rule classes are **proxy models** of `InclusionRule`, so they share its table and add no columns.
- Set `app_label` to your project's app label, or leave it out. **Don't copy `app_label = "arches_abac_permissions"`** from the built-in rules: if you do, `makemigrations` will try to write your rule's migration into this package.
- **Give the module a name the built-in rules don't use** (not `lifecycle_state_rule`, `search_rule` or `queryset_rule`). Lookup uses the first match in `INSTALLED_APPS` order, so a duplicate name could load the wrong class.

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

| Field | Value |
|---|---|
| Modulename | `my_rule.py` |
| Classname | `MyRule` |
| Definition | whatever JSON your rule class expects |

## Running tests

```bash
python manage.py test tests --settings="tests.test_settings"
```
