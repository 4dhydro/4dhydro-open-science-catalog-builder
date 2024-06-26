from operator import or_
from functools import reduce
from itertools import groupby
from typing import Dict, List, Set, Optional, TypedDict
from datetime import datetime

import pystac
from slugify import slugify

from .types_ import Product, Project, Theme, Variable, EOMission
from .stac import (
    get_theme_id,
    get_variable_id,
    get_theme_names,
    VARIABLES_PROP,
    MISSIONS_PROP,
)


class VariableSummary(TypedDict):
    years: List[int]
    numberOfProducts: int


class VariableMetrics(TypedDict):
    name: str
    description: str
    summary: VariableSummary


class ThemeSummary(TypedDict):
    years: List[int]
    numberOfProducts: int
    numberOfProjects: int
    numberOfVariables: int


class ThemeMetrics(TypedDict):
    name: str
    description: str
    image: Optional[str]
    website: str
    summary: ThemeSummary
    variables: List[VariableMetrics]


class MissionSummary(TypedDict):
    years: List[int]
    numberOfProducts: int
    numberOfVariables: int


class MissionMetrics(TypedDict):
    name: str
    summary: MissionSummary


class GlobalSummary(TypedDict):
    years: List[int]
    numberOfProducts: int
    numberOfProjects: int
    numberOfVariables: int
    numberOfThemes: int


class GlobalMetrics(TypedDict):
    id: str
    summary: GlobalSummary
    themes: List[ThemeMetrics]
    missions: List[MissionMetrics]


def build_variable_metrics():
    pass


def build_theme_metrics():
    pass


def intervals_to_years(intervals: List[List[datetime]]) -> Set[int]:
    result = set()
    for start, end in intervals:
        if start is not None and end is not None:
            result |= set(year for year in range(start.year, end.year + 1))
    return result


def extract_collection_years(collection: pystac.Collection) -> Set[int]:
    result = set()
    for start, end in collection.extent.temporal.intervals:
        if start is not None and end is not None:
            result |= set(year for year in range(start.year, end.year + 1))
    return result


def metrics(
    id: str,
    root: pystac.Collection,
) -> GlobalMetrics:
    theme_infos: dict = {
        theme.id: {
            "projects": [],
            "products": [],
            "variable_infos": [],
            "years": set(),
            "description": theme.description,
            "image": theme.get_single_link(rel="preview").href,
            "website": theme.get_single_link(rel="via").href,
        }
        for theme in root.get_child("themes").get_children()
    }

    variable_infos = {
        variable.id: {
            "name": variable.id,
            "description": variable.description,
            "themes": get_theme_names(variable),
            "products": [],
            "years": set(),
        }
        for variable in root.get_child("variables").get_children()
    }

    eo_mission_infos = {
        eo_mission.id: {
            "products": [],
            "projects": [],
            "variables": set(),
            "years": set(),
        }
        for eo_mission in root.get_child("eo-missions").get_children()
    }

    global_info = {
        "products": [],
        "projects": [],
    }

    for variable_info in variable_infos.values():
        for theme in variable_info["themes"]:
            theme_infos[theme]["variable_infos"].append(variable_info)

    for project_collection in root.get_child("projects").get_children():
        global_info["projects"].append(project_collection)
        for theme in project_collection.extra_fields.get("osc:themes", []):
            theme_infos[theme]["projects"].append(project_collection)

    for product_collection in project_collection.get_children():
        project_collection
        global_info["products"].append(product_collection)
        for theme in product_collection.extra_fields.get("osc:themes", []):
            theme_info = theme_infos[theme]
            theme_info["products"].append(product_collection)
            theme_info["years"] |= intervals_to_years(
                product_collection.extent.temporal.intervals
            )

        variable = product_collection.extra_fields["osc:variable"]
        variable_info = variable_infos[variable]
        variable_info["products"].append(product_collection)
        variable_info["years"] |= intervals_to_years(
            product_collection.extent.temporal.intervals
        )
        for eo_mission in product_collection.extra_fields.get(
            "osc:missions", []
        ):
            eo_mission_info = eo_mission_infos[eo_mission]
            eo_mission_info["products"].append(product_collection)
            eo_mission_info["variables"].add(variable)
            eo_mission_info["years"] |= intervals_to_years(
                product_collection.extent.temporal.intervals
            )

            if project_collection not in eo_mission_info["projects"]:
                eo_mission_info["projects"].append(project_collection)

    return {
        "id": id,
        "summary": {
            "years": sorted(
                reduce(
                    or_,
                    [
                        intervals_to_years(collection.extent.temporal.intervals)
                        for collection in global_info["products"]
                    ],
                )
            ),
            "numberOfProducts": len(global_info["products"]),
            "numberOfProjects": len(global_info["projects"]),
            "numberOfVariables": len(variables),
            "numberOfThemes": len(themes),
        },
        "themes": [
            {
                "name": name,
                "description": theme_info["description"],
                "image": theme_info["image"],
                "website": theme_info["website"],
                "summary": {
                    "years": sorted(theme_info["years"]),
                    "numberOfProducts": len(theme_info["products"]),
                    "numberOfProjects": len(theme_info["projects"]),
                    "numberOfVariables": len(theme_info["variable_infos"]),
                },
                "variables": [
                    {
                        "name": variable_info["name"],
                        "description": variable_info["description"],
                        "summary": {
                            "years": sorted(variable_info["years"]),
                            "numberOfProducts": len(variable_info["products"]),
                        },
                    }
                    for variable_info in theme_info["variable_infos"]
                ],
            }
            for name, theme_info in theme_infos.items()
        ],
        "missions": [
            {
                "name": name,
                "summary": {
                    "years": sorted(eo_mission_info["years"]),
                    "numberOfProducts": len(eo_mission_info["products"]),
                    "numberOfProjects": len(eo_mission_info["projects"]),
                },
            }
            for name, eo_mission_info in eo_mission_infos.items()
        ],
    }


def caclulate_metrics(
    id: str,
    root: pystac.Collection,
) -> GlobalMetrics:
    theme_infos: dict = {
        theme.id: {
            "name": theme.title,
            "num_projects": 0,
            "num_products": 0,
            "num_variables": 0,
            "years": set(),
            "description": theme.description,
            "image": (
                theme.get_single_link(rel="preview").href
                if theme.get_single_link(rel="preview")
                else None
            ),
            "website": theme.get_single_link(rel="via").href,
        }
        for theme in root.get_child("themes").get_children()
    }

    variable_infos = {
        variable.id: {
            "name": variable.title,
            "description": variable.description,
            "themes": get_theme_names(variable),
            "num_products": 0,
            "years": set(),
        }
        for variable in root.get_child("variables").get_children()
    }

    eo_mission_infos = {
        eo_mission.id: {
            "name": eo_mission.title,
            "num_products": 0,
            "num_projects": 0,
            "num_variables": 0,
            "years": set(),
        }
        for eo_mission in root.get_child("eo-missions").get_children()
    }

    global_info = {
        "num_products": 0,
        "num_projects": 0,
        "num_themes": len(theme_infos),
        "num_variables": len(variable_infos),
        "num_eo_missions": len(eo_mission_infos),
        "years": set(),
    }

    project_collections = list(root.get_child("projects").get_children())
    global_info["num_projects"] = len(project_collections)
    for project_collection in root.get_child("projects").get_children():
        theme_names = get_theme_names(project_collection)
        for theme_name in theme_names:
            theme_infos[get_theme_id(theme_name)]["num_projects"] += 1

    product_collections = list(root.get_child("products").get_children())
    global_info["num_products"] = len(product_collections)
    for product_collection in product_collections:
        years = extract_collection_years(product_collection)
        global_info["years"] |= years
        theme_names = get_theme_names(product_collection)
        for theme_name in theme_names:
            theme_info = theme_infos[get_theme_id(theme_name)]
            theme_info["num_products"] += 1
            theme_info["years"] |= years

        for variable_name in product_collection.extra_fields[VARIABLES_PROP]:
            variable_info = variable_infos[get_variable_id(variable_name)]
            variable_info["num_products"] += 1
            variable_info["years"] |= years

        for eo_mission_name in product_collection.extra_fields[MISSIONS_PROP]:
            if eo_mission_infos.get(eo_mission_name):
                eo_mission_info = eo_mission_infos[eo_mission_name]
                eo_mission_info["num_products"] += 1
                eo_mission_info["years"] |= years

    for variable_info in variable_infos.values():
        for theme_name in variable_info["themes"]:
            theme_infos[get_theme_id(theme_name)]["num_variables"] += 1

    return {
        "id": id,
        "summary": {
            "years": sorted(global_info["years"]),
            "numberOfProducts": global_info["num_products"],
            "numberOfProjects": global_info["num_projects"],
            "numberOfVariables": global_info["num_variables"],
            "numberOfThemes": global_info["num_themes"],
            "numberOfMissions": global_info["num_eo_missions"],
        },
        "themes": [
            {
                "name": theme_info["name"],
                "description": theme_info["description"],
                "image": theme_info["image"],
                "website": theme_info["website"],
                "summary": {
                    "years": sorted(theme_info["years"]),
                    "numberOfProducts": theme_info["num_products"],
                    "numberOfProjects": theme_info["num_projects"],
                    "numberOfVariables": theme_info["num_variables"],
                },
            }
            for theme_info in theme_infos.values()
        ],
        "variables": [
            {
                "name": variable_info["name"],
                "description": variable_info["description"],
                "summary": {
                    "years": sorted(variable_info["years"]),
                    "numberOfProducts": variable_info["num_products"],
                },
            }
            for variable_info in variable_infos.values()
        ],
        "eo-missions": [
            {
                "name": eo_mission_info["name"],
                "summary": {
                    "years": sorted(eo_mission_info["years"]),
                    "numberOfProducts": eo_mission_info["num_products"],
                    "numberOfProjects": eo_mission_info["num_projects"],
                },
            }
            for eo_mission_info in eo_mission_infos.values()
        ],
    }


def build_metrics__(
    id: str,
    themes: List[Theme],
    variables: List[Variable],
    missions: List[EOMission],
    projects: List[Project],
    products: List[Product],
) -> GlobalMetrics:
    # mapping: theme -> products
    #          variable -> products
    variable_product_map: Dict[str, List[Product]] = {}
    theme_product_map: Dict[str, List[Product]] = {}
    for product in products:
        for theme in product.themes:
            theme_product_map.setdefault(theme, []).append(product)
        variable_product_map.setdefault(slugify(product.variable), []).append(
            product
        )

    # mapping: theme -> project
    theme_project_map: Dict[str, List[Project]] = {}
    for project in projects:
        for theme in project.themes:
            theme_project_map.setdefault(theme, []).append(project)

    # mapping: theme -> variable metrics
    variable_metrics: Dict[str, List[VariableMetrics]] = {
        slugify(theme_name): [
            {
                "name": variable.name,
                "description": variable.description,
                "summary": {
                    "years": sorted(
                        reduce(
                            or_,
                            [
                                set(
                                    range(
                                        product.start.year, product.end.year + 1
                                    )
                                )
                                for product in variable_product_map.get(
                                    slugify(variable.name), []
                                )
                                if product.start and product.end
                            ],
                            set(),
                        )
                    ),
                    "numberOfProducts": len(
                        variable_product_map.get(slugify(variable.name), [])
                    ),
                },
            }
            for variable in theme_variables
        ]
        # groupby needs sorting first in order to work as expected
        # TODO: variable.theme -> variable.themes
        for theme_name, theme_variables in groupby(
            sorted(variables, key=lambda v: v.theme), lambda v: slugify(v.theme)
        )
    }

    # list of theme metrics
    theme_metrics: List[ThemeMetrics] = [
        {
            "name": theme.name,
            "description": theme.description,
            "image": theme.image,
            "website": theme.link,
            # "technicalOfficer": theme_coll.extra_fields["osc:technical_officer"]["name"],
            "summary": {
                "years": sorted(
                    reduce(
                        or_,
                        [
                            set(variable["summary"]["years"])
                            for variable in variable_metrics.get(
                                slugify(theme.name), []
                            )
                        ],
                        set(),
                    )
                ),
                "numberOfProducts": len(
                    theme_product_map.get(slugify(theme.name), [])
                ),
                "numberOfProjects": len(
                    theme_project_map.get(slugify(theme.name), [])
                ),
                "numberOfVariables": len(
                    variable_metrics.get(slugify(theme.name), [])
                ),
            },
            "variables": variable_metrics[
                slugify(theme.name)
            ],  # .get(theme.name, [])
        }
        for theme in themes
    ]

    # mapping: eo_mission -> Product
    mission_product_map: Dict[str, List[Product]] = {}
    for product in products:
        for mission in product.eo_missions:
            mission_product_map.setdefault(mission, []).append(product)

    mission_metrics: List[MissionMetrics] = [
        {
            "name": mission,
            "summary": {
                "years": sorted(
                    reduce(
                        or_,
                        [
                            set(range(product.start.year, product.end.year + 1))
                            for product in products
                            if product.start and product.end
                        ],
                        set(),
                    )
                ),
                "numberOfProducts": len(products),
                "numberOfVariables": len(
                    set(product.variable for product in products)
                ),
            },
        }
        for mission, products in mission_product_map.items()
    ]

    return {
        "id": id,
        "summary": {
            "years": sorted(
                reduce(
                    or_,
                    [set(theme["summary"]["years"]) for theme in theme_metrics],
                )
            ),
            "numberOfProducts": len(products),
            "numberOfProjects": len(projects),
            "numberOfVariables": len(variables),
            "numberOfThemes": len(themes),
        },
        "themes": theme_metrics,
        "missions": mission_metrics,
    }
