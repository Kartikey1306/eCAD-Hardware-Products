"""CAD dataset ingestion and the engineering semantic model.

The pipeline is strictly one-way:

    CAD file -> raw extraction -> engineering model -> domain model
             -> simulation -> deterministic validation

The CAD file is the source of truth for physical structure. Design intent the
CAD cannot carry (which part is which component, materials, joint limits,
components with no geometry) comes from hand-authored annotations. Every
engineering value is a quantity that states its epistemic status and source;
a value nobody knows is null and marked UNKNOWN, never filled in.
"""

MODEL_VERSION = "1.0.0"
