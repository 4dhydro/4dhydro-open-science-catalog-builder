import json
import os
import os.path
import shutil
from datetime import datetime, timezone
from typing import TextIO, Optional, Iterable
from urllib.parse import urlparse

import pystac
import pystac.layout
import pystac.link
import pystac.utils
from slugify import slugify

from .metrics import caclulate_metrics

from .origcsv import (
    load_orig_products,
    load_orig_projects,
    load_orig_themes,
    load_orig_variables,
    load_orig_eo_missions,
    load_orig_benchmarks,
    load_orig_processes,
)
from .stac import (
    PROJECT_PROP,
    MISSIONS_PROP,
    VARIABLES_PROP,
    THEMES_PROP,
    collection_from_product,
    collection_from_segmentation_product,
    collection_from_project,
    collection_from_processes,
    catalog_from_theme,
    catalog_from_variable,
    catalog_from_eo_mission,
    get_theme_names,
    get_theme_id,
    get_variable_id,
    get_eo_mission_id,
    FakeHTTPStacIO,
)
from .util import get_product_segmentation
import time

# to fix https://github.com/stac-utils/pystac/issues/1112
if "related" not in pystac.link.HIERARCHICAL_LINKS:
    pystac.link.HIERARCHICAL_LINKS.append("related")

from .types_ import Product

def convert_csvs(
        variables_file: TextIO,
        themes_file: TextIO,
        eo_missions_file: TextIO,
        projects_file: TextIO,
        products_file: TextIO,
        benchmarks_file: TextIO,
        processes_files: TextIO,
        out_dir: str,
        catalog_url: Optional[str],
):
    start_time = time.time()
    variables = load_orig_variables(variables_file)
    themes = load_orig_themes(themes_file)
    projects = load_orig_projects(projects_file)
    products = load_orig_products(products_file) + load_orig_benchmarks(benchmarks_file)
    segmentation_products = get_product_segmentation(products)
    eo_missions = load_orig_eo_missions(eo_missions_file)
    processes = load_orig_processes(processes_files)

    # set root structure
    root = pystac.Catalog(
        "osc_hydro",
        """4DHydro is a response to the Invitation to Tender (ITT) of the European Space Agency with reference number ESA AO/1-11298/22/I-EFin July 2022.
        It aims at: 
          To  perform a thorough assessment of the uncertainty of existing EO and LSM/HM data sets (Tier 1) related to key tECVs. 
          To generate improved tECVS datasets at 1 km spatial resolution in the selected study areas (Tier 2).  
          To perform targeted science cases to demonstrate the synchronization of EO products and LSM/HMs models for improved predictability of hydrology system at higher spatial and temporal resolutions.
          To develop tools to enhance the ability of end-users and decision-makers to extract and manipulate existing and future reanalysis and climate data sets. 
          To derive a solid scientific basis of the state-of-the-art EO retrieval systems, as well as land surface modelling capabilities that are needed to assist the EU Destination Earth initiative.
        """,
        "4DHydro's Open Science Catalog",
    )
    projects_catalog = pystac.Catalog(
        "projects", "Activities funded by ESA", "Projects"
    )
    products_catalog = pystac.Catalog(
        "products",
        "Geoscience products representing the measured or inferred values of one or more variables over a given time range and spatial area",
        "Products",
    )

    processes_catalog = pystac.Catalog(
        "processes",
        "Find all the scripts and tools you need to make the most of this catalog ",
        "Processes",
    )

    themes_catalog = pystac.Catalog(
        "themes",
        "Earth Science topics related to this project",
        "Themes",
    )
    variables_catalog = pystac.Catalog(
        "variables",
        "Geoscience, climate and environmental variables",
        "Variables",
    )

    eo_missions_catalog = pystac.Catalog(
        "eo-missions",
        "Earth Observation Satellite Missions",
        "EO Missions",
    )

    # add the first level catalogs
    # IMPORTANT: the order is important here, to ensure that the products
    # end up beneath their collection
    # see https://github.com/stac-utils/pystac/issues/1116
    root.add_child(projects_catalog)
    root.add_child(themes_catalog)
    root.add_child(variables_catalog)
    root.add_child(eo_missions_catalog)
    root.add_child(products_catalog)
    root.add_child(processes_catalog)

    themes_catalog.add_children(
        sorted(
            (catalog_from_theme(theme) for theme in themes),
            key=lambda catalog: catalog.id,
        )
    )
    variables_catalog.add_children(
        sorted(
            (catalog_from_variable(variable) for variable in variables),
            key=lambda catalog: catalog.id,
        )
    )
    eo_missions_catalog.add_children(
        sorted(
            (catalog_from_eo_mission(eo_mission) for eo_mission in eo_missions),
            key=lambda catalog: catalog.id,
        )
    )
    projects_catalog.add_children(
        sorted(
            (collection_from_project(project) for project in projects),
            key=lambda collection: collection.id,
        )
    )
    processes_catalog.add_children(
        sorted(
            (collection_from_processes(process) for process in processes),
            key=lambda collection: collection.id,
        )
    )
    products_catalog.add_children(
        sorted(
            (collection_from_segmentation_product(parent) for parent in segmentation_products),
            key=lambda collection: collection.id,
        )
    )

    projects_catalog.add_children(
        sorted(
            (collection_from_project(project) for project in projects),
            key=lambda collection: collection.id,
        )
    )

    def _link_sub_product(catalog: pystac.Catalog, products_interface: list[Product]) -> None:
        for line_product in products_interface:
            parent: list[pystac.Catalog] = list(
                filter(lambda x: x.title == line_product.collection, catalog.get_children()))
            if len(parent) != 0:
                parent[0].add_child(collection_from_product(line_product))
            else:
                catalog.add_child(collection_from_product(line_product))

    _link_sub_product(products_catalog, products)

    # save catalog
    root.normalize_and_save(out_dir, pystac.CatalogType.SELF_CONTAINED)

    # TODO: move theme images if exist
    if os.path.isdir("images"):
        for catalog in themes_catalog.get_children():
            link = catalog.get_single_link(rel="preview")
            if link:
                out_path = os.path.join(
                    os.path.dirname(catalog.get_self_href()), link.href
                )
                shutil.copyfile(
                    os.path.join("images", link.href),
                    out_path,
                )

    print(f"--- {((time.time() - start_time)/60)} minutes ---")
    print("-------------END CONVERT --------------")


def validate_project(
    collection: pystac.Collection, themes: set[str]
) -> list[str]:
    errors = []
    for theme in collection.extra_fields[THEMES_PROP]:
        if theme not in themes:
            errors.append(f"Theme '{theme}' not valid")
    return errors


def validate_product(
    collection: pystac.Collection,
    themes: set[str],
    variables: set[str],
    eo_missions: set[str],
) -> list[str]:
    errors = []
    variable = collection.extra_fields[VARIABLES_PROP]
    if variable not in variables:
        errors.append(f"Variable '{variable}' not valid")
    for theme in collection.extra_fields[THEMES_PROP]:
        if theme not in themes:
            errors.append(f"Theme '{theme}' not valid")
    for eo_mission in collection.extra_fields[MISSIONS_PROP]:
        if eo_mission not in eo_missions:
            errors.append(f"EO Mission '{eo_mission}' not valid")
    return errors


def validate_catalog(data_dir: str):
    root: pystac.Collection = pystac.read_file(
        os.path.join(data_dir, "collection.json")
    )
    assets = root.get_assets()
    with open(os.path.join(data_dir, assets["themes"].href)) as f:
        themes = {theme["name"] for theme in json.load(f)}
    with open(os.path.join(data_dir, assets["variables"].href)) as f:
        variables = {variable["name"] for variable in json.load(f)}
    with open(os.path.join(data_dir, assets["eo-missions"].href)) as f:
        eo_missions = {eo_mission["name"] for eo_mission in json.load(f)}

    validation_errors = []

    for project_collection in root.get_children():
        ret = validate_project(project_collection, themes)
        if ret:
            validation_errors.append((project_collection, ret))
        for product_collection in project_collection.get_children():
            ret = validate_product(
                product_collection, themes, variables, eo_missions
            )
            if ret:
                validation_errors.append((product_collection, ret))

    from pprint import pprint

    pprint(validation_errors)
    # TODO: raise Exception if validation_errors


def set_update_timestamps(
    catalog: pystac.Catalog, stac_io: pystac.StacIO
) -> Optional[datetime]:
    """Updates the `updated` field in the catalog according to the underlying
    files last modification time and its included Items and children. This also
    updates the included STAC Items `updated` property respectively.

    This function recurses into its child catalogs.

    The resulting `updated` time is the latest of the following:

        - the child catalogs `updated` timestamp, which are resolved first
        - its directly included items
        - the modification time of the catalog file itself

    Args:
        catalog (pystac.Catalog): the catalog to update the timestamp for

    Returns:
        Optional[datetime]: the resulting timestamp
    """

    io = None
    if isinstance(stac_io, FakeHTTPStacIO):
        io = stac_io

    href = catalog.get_self_href()
    path = io._replace_path(href) if io else href

    if urlparse(path).scheme not in ("", "file"):
        return None

    updated = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)

    for child_link in catalog.get_child_links():
        # only follow relative links
        if urlparse(child_link.get_href()).scheme not in ("", "file"):
            continue
        child = child_link.resolve_stac_object().target
        child_updated = set_update_timestamps(child, stac_io)
        if child_updated:
            updated = max(updated, child_updated)

    for item in catalog.get_items():
        href = item.get_self_href()
        path = io._replace_path(href) if io else href

        if urlparse(path).scheme not in ("", "file"):
            continue

        item_updated = datetime.fromtimestamp(
            os.path.getmtime(path), tz=timezone.utc
        )
        pystac.CommonMetadata(item).updated = item_updated
        updated = max(updated, item_updated)

    if updated:
        pystac.CommonMetadata(catalog).updated = updated

    return updated


def make_collection_assets_absolute(collection: pystac.Collection):
    for asset in collection.assets.values():
        asset.href = pystac.utils.make_absolute_href(
            asset.href, collection.get_self_href()
        )


def link_collections(
    product_collections: Iterable[pystac.Collection],
    project_collections: Iterable[pystac.Collection],
    theme_catalogs: Iterable[pystac.Catalog],
    variable_catalogs: Iterable[pystac.Catalog],
    eo_mission_catalogs: Iterable[pystac.Catalog],
    processes_collections: Iterable[pystac.Collection],
):
    themes_map: dict[str, pystac.Catalog] = {
        catalog.id: catalog for catalog in theme_catalogs
    }
    variables_map: dict[str, pystac.Catalog] = {
        catalog.id: catalog for catalog in variable_catalogs
    }
    eo_missions_map: dict[str, pystac.Catalog] = {
        catalog.id: catalog for catalog in eo_mission_catalogs
    }
    project_map: dict[str, pystac.Collection] = {
        collection.id: collection for collection in project_collections
    }

    # link variable -> themes
    for variable_catalog in variable_catalogs:
        variable_catalog.add_links(
            [
                pystac.Link(
                    rel="related",
                    target=themes_map[theme_name],
                    media_type="application/json",
                    title=f"Theme: {themes_map[theme_name].title}",
                )
                for theme_name in get_theme_names(validate_catalog)
            ]
        )

    # link projects -> themes
    for project_collection in project_collections:
        project_collection.add_links(
            [
                pystac.Link(
                    rel="related",
                    target=themes_map[theme],
                    media_type="application/json",
                    title=f"Theme: {themes_map[theme].title}",
                )
                for theme in get_theme_names(project_collection)
            ]
        )

    # link processes -> project
    for process_collection in processes_collections:
        project_collection = project_map[
            slugify(process_collection.extra_fields[PROJECT_PROP])
        ]
        process_collection.add_link(
            pystac.Link(
                rel="related",
                target=project_collection,
                media_type="application/json",
                title=f"Project: {project_collection.title}",
            )
        )

    def _links_all_products(product_interface_collections:Iterable[pystac.Collection])-> None:
        for product_collection in product_interface_collections:
            # product -> project
            project_collection = project_map[
                slugify(product_collection.extra_fields[PROJECT_PROP])
            ]
            product_collection.add_link(
                pystac.Link(
                    rel="related",
                    target=project_collection,
                    media_type="application/json",
                    title=f"Project: {project_collection.title}",
                )
            )
            project_collection.add_child(product_collection, set_parent=True)

            # product -> themes
            for theme_name in get_theme_names(product_collection):
                theme_catalog = themes_map[get_theme_id(theme_name)]
                product_collection.add_link(
                    pystac.Link(
                        rel="related",
                        target=theme_catalog,
                        media_type="application/json",
                        title=f"Theme: {theme_catalog.title}",
                    )
                )
                theme_catalog.add_child(product_collection, set_parent=True)

            # product -> variables
            for variable_name in product_collection.extra_fields[VARIABLES_PROP]:
                variable_catalog = variables_map[get_variable_id(variable_name)]
                product_collection.add_link(
                    pystac.Link(
                        rel="related",
                        target=variable_catalog,
                        media_type="application/json",
                        title=f"Variable: {variable_catalog.title}",
                    )
                )
                variable_catalog.add_child(product_collection, set_parent=True)

            # product -> eo mission
            for eo_mission in product_collection.extra_fields[MISSIONS_PROP]:
                eo_mission_catalog = eo_missions_map[get_eo_mission_id(eo_mission)]
                product_collection.add_link(
                    pystac.Link(
                        rel="related",
                        target=eo_mission_catalog,
                        media_type="application/json",
                        title=f"EO Mission: {eo_mission_catalog.title}",
                    )
                )
                eo_mission_catalog.add_child(product_collection, set_parent=True)


    # link products
    _links_all_products(product_collections)



# TODO: apply keywords
# def apply_keywords()


def build_dist(
    data_dir: str,
    out_dir: str,
    root_href: str,
    add_iso_metadata: bool = True,
    pretty_print: bool = True,
    update_timestamps: bool = True,
):
    start_time = time.time()
    shutil.copytree(
        data_dir,
        out_dir,
    )
    root: pystac.Catalog = pystac.read_file(
        os.path.join(out_dir, "catalog.json")
    )
    root.extra_fields.setdefault("conformsTo", [
        "https://api.stacspec.org/v1.0.0/core",
    ])

    if update_timestamps:
        set_update_timestamps(root, None)

    link_collections(
        root.get_child("products").get_children(),
        root.get_child("projects").get_children(),
        root.get_child("themes").get_children(),
        root.get_child("variables").get_children(),
        root.get_child("eo-missions").get_children(),
        root.get_child("processes").get_children(),
    )

    # Apply keywords
    from itertools import chain
    catalogs = chain(
        root.get_child("products").get_children(),
        root.get_child("projects").get_children(),
        root.get_child("themes").get_children(),
        root.get_child("variables").get_children(),
        root.get_child("eo-missions").get_children(),
        root.get_child("processes").get_children(),
    )
    from .stac import apply_keywords
    for catalog in catalogs:
        apply_keywords(catalog)

    root.save(pystac.CatalogType.SELF_CONTAINED, dest_href=out_dir)
    print(f"--- {((time.time() - start_time) / 60)} minutes ---")
    print("-------------END BUILD --------------")


def build_metrics(    data_dir: str,
    metrics_file_name: str,
    add_to_root: bool,
    pretty_print: bool = True,
):
    root: pystac.Catalog = pystac.read_file(
        os.path.join(data_dir, "catalog.json")
    )

    metrics = caclulate_metrics("OSC-Catalog", root)

    with open(os.path.join(data_dir, metrics_file_name), "w") as f:
        json.dump(metrics, f, indent=2 if pretty_print else None)

    if add_to_root:
        root.add_link(
            pystac.Link(
                rel="alternate",
                target=metrics_file_name,
                media_type="application/json",
                title="Metrics",
            )
        )
    root.save_object()
