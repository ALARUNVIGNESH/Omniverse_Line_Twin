"""Real UsdShade/UsdPreviewSurface materials for the paint variants.

The original body asset only set displayColor per variant - a flat viewport
preview color, not a shaded material. This authors an actual UsdPreviewSurface
material per variant (diffuse color, roughness, metallic, clearcoat) and
binds it inside that variant's own edit context, so selecting a paint variant
switches the bound *material*, not just a display color.

Materials are defined once, unconditionally, under /Body/Materials - so all
three exist on the stage regardless of which variant happens to be selected
at authoring time. Only the binding on /Body/Shell is variant-gated. This
matters: if the materials themselves were authored inside a variant edit
context, only the last variant looped over would actually end up composed,
since /Body/Materials would then only exist under that one variant's arc.

UsdPreviewSurface is the render-delegate-agnostic material standard - Kit,
Unreal's USD plugin, and usdview all resolve it directly, so no
per-engine re-authoring is needed for the same paint to render consistently
across every client this project touches.

Clearcoat is included because automotive paint is a two-layer finish (base
coat + a separate clear top coat) - gloss and racing-blue lean into that
with a strong clearcoat; matte black has none, which is exactly what makes
it look matte rather than "black but shiny."
"""

from __future__ import annotations

from pxr import Gf, Sdf, Usd, UsdShade

from line_twin.build_stage import BODY_PATH, PAINT_VARIANTS

# Tuned per finish, not just per color - gloss and matte are meaningfully
# different materials, not the same shader with a different diffuseColor.
PAINT_MATERIAL_PARAMS = {
    "gloss_white": {"roughness": 0.15, "metallic": 0.0, "clearcoat": 0.9, "clearcoat_roughness": 0.03},
    "racing_blue": {"roughness": 0.20, "metallic": 0.0, "clearcoat": 0.9, "clearcoat_roughness": 0.05},
    "matte_black": {"roughness": 0.75, "metallic": 0.0, "clearcoat": 0.0, "clearcoat_roughness": 0.5},
}


def _define_material(stage: Usd.Stage, variant_name: str, rgb: tuple) -> UsdShade.Material:
    params = PAINT_MATERIAL_PARAMS[variant_name]
    material_path = f"/Body/Materials/{variant_name}"
    material = UsdShade.Material.Define(stage, material_path)

    shader = UsdShade.Shader.Define(stage, f"{material_path}/PreviewSurface")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(params["roughness"])
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(params["metallic"])
    shader.CreateInput("clearcoat", Sdf.ValueTypeNames.Float).Set(params["clearcoat"])
    shader.CreateInput("clearcoatRoughness", Sdf.ValueTypeNames.Float).Set(params["clearcoat_roughness"])
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def add_paint_materials(stage: Usd.Stage) -> None:
    """Author one material per paint variant and bind it inside that
    variant's own edit context on /Body/Shell."""
    body_prim = stage.GetPrimAtPath("/Body")
    shell = stage.GetPrimAtPath("/Body/Shell")
    vset = body_prim.GetVariantSets().GetVariantSet("paint")

    materials = {
        name: _define_material(stage, name, rgb) for name, rgb in PAINT_VARIANTS.items()
    }

    original_selection = vset.GetVariantSelection()
    for variant_name in PAINT_VARIANTS:
        vset.SetVariantSelection(variant_name)
        with vset.GetVariantEditContext():
            UsdShade.MaterialBindingAPI.Apply(shell).Bind(materials[variant_name])
    vset.SetVariantSelection(original_selection)


def augment_body_asset_with_materials(path=BODY_PATH) -> None:
    """Open an already-built body.usda and add materials to it in place."""
    stage = Usd.Stage.Open(str(path))
    add_paint_materials(stage)
    stage.GetRootLayer().Save()


if __name__ == "__main__":
    augment_body_asset_with_materials()
