import bpy

from .selection import selected_uv_face_indices_by_object


def _create_mask_material(name, color, image):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = color
    emission.inputs["Strength"].default_value = 1.0
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = image
    nodes.active = image_node
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def bake_selected_uv_mask(context, objects, image_name, resolution, margin):
    if hasattr(objects, "data"):
        objects = [objects]

    if isinstance(resolution, int):
        width = height = resolution
    else:
        width, height = resolution

    selected_by_object = selected_uv_face_indices_by_object(objects)
    if not selected_by_object:
        return None, "Select at least one UV face"

    scene = context.scene
    original_engine = scene.render.engine
    original_active = context.view_layer.objects.active
    original_selected = list(context.selected_objects)
    temp_objects = []
    temp_meshes = []
    temp_materials = []
    image = None

    try:
        bpy.ops.object.mode_set(mode="OBJECT")
        image = bpy.data.images.new(image_name, width=width, height=height, alpha=True)
        image.generated_color = (0.0, 0.0, 0.0, 1.0)
        image.colorspace_settings.name = "Non-Color"

        black_material = _create_mask_material(
            ".UVIslandMaskBlack", (0.0, 0.0, 0.0, 1.0), image
        )
        white_material = _create_mask_material(
            ".UVIslandMaskWhite", (1.0, 1.0, 1.0, 1.0), image
        )
        temp_materials.extend((black_material, white_material))

        for obj, selected_face_indices in selected_by_object.items():
            temp_mesh = obj.data.copy()
            temp_mesh.name = ".UVIslandMaskMesh"
            temp_meshes.append(temp_mesh)
            temp_object = bpy.data.objects.new(".UVIslandMaskObject", temp_mesh)
            temp_objects.append(temp_object)
            temp_object.matrix_world = obj.matrix_world.copy()
            context.collection.objects.link(temp_object)

            temp_mesh.materials.clear()
            temp_mesh.materials.append(black_material)
            temp_mesh.materials.append(white_material)
            for polygon in temp_mesh.polygons:
                polygon.material_index = 1 if polygon.index in selected_face_indices else 0

        bpy.ops.object.select_all(action="DESELECT")
        for temp_object in temp_objects:
            temp_object.select_set(True)
        context.view_layer.objects.active = temp_objects[0]
        scene.render.engine = "CYCLES"
        bpy.ops.object.bake(type="EMIT", margin=margin, margin_type="EXTEND", use_clear=False)
        image.update()
    except Exception:
        if image is not None:
            bpy.data.images.remove(image)
            image = None
        raise
    finally:
        for temp_object in temp_objects:
            bpy.data.objects.remove(temp_object, do_unlink=True)
        for temp_mesh in temp_meshes:
            bpy.data.meshes.remove(temp_mesh)
        for material in temp_materials:
            bpy.data.materials.remove(material)

        scene.render.engine = original_engine
        for selected_object in original_selected:
            selected_object.select_set(True)
        context.view_layer.objects.active = original_active
        if original_active is not None:
            original_active.select_set(True)
            bpy.ops.object.mode_set(mode="EDIT")

    return image, None
