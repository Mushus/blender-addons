---
name: blender-addon-i18n
description: Add or update Japanese UI translations in a Blender add-on while preserving reload-safe registration. Use when an add-on needs localized labels, descriptions, panel text, operator text, or reports.
targets: ["agentsskills"]
agentsskills:
  metadata:
    version: "1.0.0"
---

# Blender Add-on i18n

Add `i18n.py` beside the add-on modules. Define `TRANSLATIONS` as Blender translation keys and register it with `bpy.app.translations.register(__name__, TRANSLATIONS)`; unregister it with the matching `unregister(__name__)` call.

Translate every user-facing source string used by the add-on:

- `bl_info` name and description
- embedded-host display and group labels
- panel labels and button text
- `PropertyGroup` names and descriptions
- operator `bl_label` and `bl_description`
- `self.report()` messages

Use `("*", source_text)` for normal interface strings and `("Operator", source_text)` for operator labels or descriptions when Blender supplies that context. Keep source text exactly equal to the Python string. For report strings, pass the source text through `bpy.app.translations.pgettext_iface()` before calling `self.report()`.

Integrate translations with the add-on lifecycle:

1. Add `i18n` to the package reload list.
2. Import it in the package binding function.
3. Register translations before classes and store `i18n_module.unregister` in the durable runtime state.
4. Extend `runtime.begin_state()` with `i18n_unregister` and call that saved callback from `runtime.uninstall()` even after a module reload.
5. Retain the existing durable `driver_namespace` cleanup and host unregistration behavior; do not use module globals for cleanup.

Use `addons/uv_island_mask/i18n.py`, its `runtime.py`, and its package `__init__.py` as the repository pattern. Do not translate Blender built-in strings or modify an unrelated add-on.

Validate with the add-on's lifecycle smoke test: enable/disable, reload while enabled, and a repeated `register()` must leave no registered translation domain, classes, Scene properties, or runtime state. Run the repository quality gate and package validation after the change.