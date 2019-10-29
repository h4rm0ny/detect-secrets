try:
    from functools import lru_cache
except ImportError:  # pragma: no cover
    from functools32 import lru_cache

import inspect
import os
from abc import abstractproperty
try:
    import importlib.util
except ImportError:  # pragma: no cover
    import imp

from detect_secrets.util import get_root_directory
from detect_secrets.util import is_python_2


def change_custom_plugin_paths_to_tuple(custom_plugin_paths_function):
    """
    :type custom_plugin_paths_function: function
    A function that takes one argument named custom_plugin_paths

    :returns: function
    The custom_plugin_paths_function with it's arg changed to a tuple
    """
    def wrapper_of_custom_plugin_paths_function(custom_plugin_paths):
        return custom_plugin_paths_function(tuple(custom_plugin_paths))

    return wrapper_of_custom_plugin_paths_function


@change_custom_plugin_paths_to_tuple
@lru_cache(maxsize=1)
def get_mapping_from_secret_type_to_class_name(custom_plugin_paths):
    """Returns dictionary of secret_type => plugin classname"""
    return {
        plugin.secret_type: name
        for name, plugin in import_plugins(custom_plugin_paths).items()
    }


def _dynamically_import_module(path_to_import, module_name):
    """
    :type path_to_import: str
    :type module_name: str

    :rtype: module
    """
    if is_python_2():  # pragma: no cover
        return imp.load_source(
            module_name,
            path_to_import,
        )

    spec = importlib.util.spec_from_file_location(
        module_name,
        path_to_import,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_valid_concrete_plugin_class(attr):
    """
    :type attr: Any

    :rtype: bool
    """
    if (
        not inspect.isclass(attr)
        or
        # Python 2 only:
        # Old-style classes do not have the __mro__ attribute
        not hasattr(attr, '__mro__')
    ):
        return False

    # Dynamically imported classes have different
    # addresses for the same functions as statically
    # imported classes do, so issubclass does not work.
    # We use __mro__ to loop through all parent classes.
    # issubclass does work in Python 3, since parent classes
    # do have the same addresses.
    if not any(
        'plugins.base.BasePlugin' in str(klass)
        for klass in attr.__mro__
    ):
        return False

    # Use this as a heuristic to determine abstract classes
    if isinstance(attr.secret_type, abstractproperty):
        return False

    return True


@change_custom_plugin_paths_to_tuple
@lru_cache(maxsize=1)
def import_plugins(custom_plugin_paths):
    """
    :type custom_plugin_paths: tuple(str,)
    :param custom_plugin_paths: possibly empty tuple of paths that have custom plugins.

    :rtype: Dict[str, Type[TypeVar('Plugin', bound=BasePlugin)]]
    """
    path_and_module_name_pairs = []

    # Handle files
    for path_to_import in custom_plugin_paths:
        if os.path.isfile(path_to_import):
            # [:-3] for removing '.py'
            module_name = path_to_import[:-3].replace('/', '.')
            path_and_module_name_pairs.append(
                (
                    path_to_import,
                    module_name,
                ),
            )

    # Handle directories
    regular_plugins_dir = os.path.join(
        get_root_directory(),
        'detect_secrets/plugins',
    )
    plugin_dirs = (
        [regular_plugins_dir]
        +
        list(
            filter(
                lambda path: (
                    os.path.isdir(path)
                ),
                custom_plugin_paths,
            ),
        )
    )
    for plugin_dir in plugin_dirs:
        for filename in os.listdir(
            plugin_dir,
        ):
            if (
                filename.startswith('_')
                or not filename.endswith('.py')
            ):
                continue

            if plugin_dir == regular_plugins_dir:
                # Remove absolute path
                plugin_dir = 'detect_secrets/plugins'

            path_to_import = os.path.join(
                plugin_dir,
                filename,
            )

            # [:-3] for removing '.py'
            module_name = path_to_import[:-3].replace('/', '.')
            path_and_module_name_pairs.append(
                (
                    path_to_import,
                    module_name,
                ),
            )

    # Do the importing
    plugins = {}
    for path_to_import, module_name in path_and_module_name_pairs:
        module = _dynamically_import_module(
            path_to_import,
            module_name,
        )
        for attr_name in filter(
            lambda attr_name: not attr_name.startswith('_'),
            dir(module),
        ):
            attr = getattr(module, attr_name)
            if _is_valid_concrete_plugin_class(attr):
                plugins[attr_name] = attr

    return plugins
