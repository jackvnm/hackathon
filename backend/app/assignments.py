from dataclasses import dataclass

from app.models import Analysis, Assignment


@dataclass(frozen=True)
class CrewDefinition:
    department: str
    capabilities: frozenset[str]
    inspection_capability: str


CREWS = {
    "roads": CrewDefinition("Roads Maintenance", frozenset({"road_surface_repair", "footpath_repair", "road_marking", "roads_inspection"}), "roads_inspection"),
    "cleanup": CrewDefinition("Waste Management", frozenset({"dumped_item_removal", "abandoned_item_removal", "litter_removal", "cleanup_inspection"}), "cleanup_inspection"),
    "graffiti": CrewDefinition("Graffiti Removal", frozenset({"graffiti_removal", "graffiti_inspection"}), "graffiti_inspection"),
    "lighting": CrewDefinition("Public Lighting", frozenset({"lighting_inspection"}), "lighting_inspection"),
    "arborist": CrewDefinition("Parks", frozenset({"arborist_inspection"}), "arborist_inspection"),
    "drainage": CrewDefinition("Drainage", frozenset({"drainage_inspection"}), "drainage_inspection"),
}

# category -> crew, default task type, required capability
CATEGORIES = {
    "Report Problem Road Surface": ("roads", "repair", "road_surface_repair"),
    "Report Problem Footpath": ("roads", "repair", "footpath_repair"),
    "Repaint Existing Road Markings": ("roads", "repair", "road_marking"),
    "Illegal Dumping": ("cleanup", "removal", "dumped_item_removal"),
    "Abandoned Bicycles or Trolleys": ("cleanup", "removal", "abandoned_item_removal"),
    "Report Litter Offence": ("cleanup", "removal", "litter_removal"),
    "Report Graffiti": ("graffiti", "removal", "graffiti_removal"),
    "Public Lighting Repairs": ("lighting", "inspection", "lighting_inspection"),
    "Tree Maintenance": ("arborist", "inspection", "arborist_inspection"),
    "Report Gully Problem": ("drainage", "inspection", "drainage_inspection"),
    "Report Sewer Problem": ("drainage", "inspection", "drainage_inspection"),
}


def assign_analysis(analysis: Analysis) -> tuple[Analysis, Assignment]:
    definition = CATEGORIES.get(analysis.category)
    if definition is None:
        return analysis.model_copy(update={"needs_review": True, "time_cost_minutes": None}), Assignment()
    crew, default_task, required_capability = definition
    crew_definition = CREWS[crew]
    task_type = "inspection" if analysis.needs_inspection else default_task
    duration = analysis.time_cost_minutes
    needs_inspection = analysis.needs_inspection or default_task == "inspection"
    needs_review = analysis.needs_review or needs_inspection

    if needs_inspection:
        required_capability = crew_definition.inspection_capability
        # Never reuse a repair estimate when backend rules require inspection.
        if not analysis.needs_inspection:
            duration = None

    capabilities = set(analysis.required_capabilities)
    if not capabilities:
        capabilities = {required_capability}
    elif required_capability not in capabilities or not capabilities <= crew_definition.capabilities:
        needs_review = True
        duration = None
        capabilities.add(required_capability)

    updated = analysis.model_copy(update={
        "needs_inspection": needs_inspection,
        "needs_review": needs_review,
        "time_cost_minutes": duration,
        "required_capabilities": sorted(capabilities),
    })
    return updated, Assignment(crew=crew, task_type=task_type, estimated_minutes=duration)
