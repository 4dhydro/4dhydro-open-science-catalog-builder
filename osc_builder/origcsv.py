from datetime import date, datetime, time, timezone
from typing import List, Literal, TextIO, Union, cast, Optional, Tuple
import csv
import json
from urllib.parse import urlparse

from pygeoif import geometry
from dateutil.parser import parse as parse_datetime
from slugify import slugify

from .types_ import Contact, Product, Project, Status, Theme, Variable, EOMission, Benchmark, Processes
from .util import parse_decimal_date, get_depth

def get_metadata_column() -> dict:
    return {
        "EO Missions": 3,
        "WP1 Products": 26,
        "WP2 Products": 26,
        "WP5 Products": 26,
        "Projects": 10,
        "Themes": 4,
        "Variables": 4,
        "Benchmarks": 26,
        "Processes": 8,
    }

def get_themes(obj: dict) -> List[str]:
    return [obj[f"Theme{i}"] for i in range(1, 4) if obj[f"Theme{i}"]]


def parse_geometry(source: str) -> geometry._Geometry:
    geom = None
    if not source:
        pass
    elif source.startswith("Multipolygon"):
        # TODO: figure out a way to parse this
        pass
    else:
        try:
            raw_geom = json.loads(source)
            depth = get_depth(raw_geom)
            if depth == 1:
                geom = geometry.Point(*raw_geom)
            elif depth == 3:
                shell, *holes = raw_geom
                geom = geometry.Polygon(shell, holes or None)
        except ValueError:
            pass

    return geom


def parse_released(value: str) -> Union[date, None, Literal["Planned"]]:
    if not value:
        return None

    if value == "Planned" or value.lower() == "planned":
        return "Planned"

    return parse_datetime(value).date()


def parse_list(value: str, delimiter: str = ";") -> List[str]:
    return [
        stripped
        for item in value.split(delimiter)
        if (stripped := item.strip())
    ]


def parse_date(value: str, is_max: bool) -> Optional[datetime]:
    if not value:
        return None

    return datetime.combine(
        cast(datetime, parse_decimal_date(value)),
        time.max.replace(microsecond=0) if is_max else time.min,
        timezone.utc,
    )


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    start = datetime.combine(
        parse_datetime(value).date(),
        time.min,
        tzinfo=timezone.utc,
    )
    return start

def load_orig_products(file: TextIO) -> List[Product]:
    products = [
        Product(
            id=line["Short_Name"],
            website=line.get("Website"),
            title=line["Product"],
            description=line["Description"],
            project=line["Project"],
            variables=parse_list(line["Variables"]),
            themes=get_themes(line),
            access=line["Access"],
            notebook=line["Notebook"],
            doi=urlparse(line["DOI"]).path[1:] if line["DOI"] else None,
            start=_parse_date(line["Start"]),
            end=_parse_date(line["End"]),
            geometry=parse_geometry(line["Polygon"]),
            region=line["Region"] or None,
            released=parse_released(line["Released"]),
            eo_missions=parse_list(line["EO_Missions"]),
            keywords=parse_list(line["Keywords"]) if "Keywords" in line else [],
            format=line["Format"] or None,
            category=line["Category"] or None,
            coordinate=line["Coordinate"] or None,
            spatial_resolution=line["Spatial Resolution"] or None,
            temporal_resolution=line["Temporal Resolution"] or None,
            collection=line["Collection"] or None,
            provider=line["Consortium"] or None
        )
        for line in csv.DictReader(file)
    ]
    return products

def load_orig_benchmarks(file: TextIO) -> List[Benchmark]:
    benchmarks = [
        Benchmark(
            id=line["Short_Name"],
            website=line.get("Website"),
            title=line["Product"],
            description=line["Description"],
            project=line["Project"],
            variables=parse_list(line["Variables"]),
            themes=get_themes(line),
            access=line["Access"],
            notebook=line["Notebook"],
            doi=urlparse(line["DOI"]).path[1:] if line["DOI"] else None,
            start=_parse_date(line["Start"]),
            end=_parse_date(line["End"]),
            geometry=parse_geometry(line["Polygon"]),
            region=line["Region"] or None,
            released=parse_released(line["Released"]),
            eo_missions=parse_list(line["EO_Missions"]),
            keywords=parse_list(line["Keywords"]) if "Keywords" in line else [],
            format=line["Format"] or None,
            category=line["Category"] or None,
            coordinate=line["Coordinate"] or None,
            spatial_resolution=line["Spatial Resolution"] or None,
            temporal_resolution=line["Temporal Resolution"] or None,
            collection=line["Collection"] or None,
            provider=line["Consortium"] or None
        )
        for line in csv.DictReader(file)
    ]
    return benchmarks

def load_orig_projects(file: TextIO) -> List[Project]:
    projects = [
        Project(
            id=slugify(line["Short_Name"]),
            status=Status(line["Status"].upper()),
            name=line["Project_Name"],
            title=line["Short_Name"],
            description=line["Short_Description"],
            website=line["Website"],
            consortium=parse_list(line["Consortium"], ","),
            start=_parse_date(line["Start_Date_Project"]),
            end=_parse_date(line["End_Date_Project"]),
            technical_officer=Contact(
                line["TO"],
                line["TO_E-mail"],
            ),
        )
        for line in csv.DictReader(file)
    ]
    return projects

def load_orig_themes(file: TextIO) -> List[Theme]:
    return [
        Theme(
            name=line["theme"],
            description=line["description"] if line["description"] else "" ,
            link=line["link"],
            image=line.get("image"),
        )
        for line in csv.DictReader(file)
    ]

def load_orig_variables(file: TextIO) -> List[Variable]:
    return [
        Variable(
            name=line["variable"],
            description=line["variable description"],
            link=line["link"],
            themes=parse_list(line["themes"]),
        )
        for line in csv.DictReader(file)
    ]

def load_orig_processes(file: TextIO) -> List[Processes]:
    return [
        Processes(
            project=line["Project"],
            name=line["Name"],
            description=line["Description"],
            link=line["Link"],
            asset=line["Asset"],
            released=parse_released(line["Released"]),
            languages=parse_list(line["Languages"])
        )
        for line in csv.DictReader(file)
    ]

def load_orig_eo_missions(file: TextIO) -> List[EOMission]:
    return [
        EOMission(
            name=line["EO_Missions"],
            description=line["Description"] if line["Description"] else "",
            link=line["Link"]
        )
        for line in csv.DictReader(file)
    ]


def validate_csvs(
        variables_file: TextIO,
        themes_file: TextIO,
        missions_file: TextIO,
        projects_file: TextIO,
        products_wp1_file: TextIO,
        products_wp2_file: TextIO,
        products_wp5_file: TextIO,
        processes_file: TextIO,
) -> List[str]:
    THEMES = {
        line["theme"].strip(): line for line in csv.DictReader(themes_file)
    }
    VARIABLES = {
        line["variable"].strip(): line
        for line in csv.DictReader(variables_file)
    }
    MISSIONS = {
        line["EO_Missions"].strip(): line
        for line in csv.DictReader(missions_file)
    }
    PROJECTS = {
        line["Short_Name"].strip(): line
        for line in csv.DictReader(projects_file)
    }
    PRODUCTS_WP1 = {
        line["Product"].strip(): line for line in csv.DictReader(products_wp1_file)
    }
    PRODUCTS_WP2 = {
        line["Product"].strip(): line for line in csv.DictReader(products_wp2_file)
    }
    PRODUCTS_WP5 = {
        line["Product"].strip(): line for line in csv.DictReader(products_wp5_file)
    }

    issues = []

    def _valid_length_file(file_input: TextIO, name_file: str):
        file_input.seek(0)
        file_reader = csv.reader(file_input)
        file_column_name = next(file_reader)
        if len(file_column_name) != get_metadata_column()[name_file]:
            issues.append(
                f"""{name_file} csv file is corrupted, this csv must have {get_metadata_column()[name_file]}
                             columns but {len(file_column_name)} got. """
            )


    _valid_length_file(projects_file, "Projects")
    _valid_length_file(variables_file, "Variables")
    _valid_length_file(missions_file, "EO Missions")
    _valid_length_file(processes_file, "Processes")
    _valid_length_file(products_wp1_file, "WP1 Products")
    _valid_length_file(products_wp2_file, "WP2 Products")
    _valid_length_file(products_wp5_file, "WP5 Products")



    for name, variable in VARIABLES.items():
        for theme in parse_list(
                variable.get("themes") or variable.get("theme")
        ):
            if theme not in THEMES:
                issues.append(
                    f"Variable '{name}' references non-existing theme '{theme}'"
                )

    def _validate_products(product_interface: dict, element:str) -> list[str]:
        _issues = []
        for name, product in product_interface.items():
            project = product["Project"]
            if product["Project"] not in PROJECTS:
                _issues.append(
                    f"{element} '{name}' references non-existing project '{project}'"
                )

            if product["Product"] is None or product["Product"] == '':
                _issues.append(
                    f"{element} missing product column \"product\" for the line {product['ID']}"
                )

            if product["Collection"] is None or product["Collection"] == '':
                _issues.append(
                    f"{element} '{name}' has not collection linked please add collection for the product"
                )

            for theme in get_themes(product):
                if theme not in THEMES:
                    _issues.append(
                        f"{element} '{name}' references non-existing theme '{theme}'"
                    )

            for variable in parse_list(product["Variables"]):
                if variable not in VARIABLES:
                    _issues.append(
                        f"{element} '{name}' references non-existing variable '{variable}'"
                    )

            for mission in parse_list(product["EO_Missions"]):
                if mission not in MISSIONS:
                    _issues.append(
                        f"{element} '{name}' references non-existing mission '{mission}'"
                    )
        return _issues

    issues = issues + _validate_products(PRODUCTS_WP1, "WP1_Tier1_Products")
    issues = issues + _validate_products(PRODUCTS_WP2, "WP2_Tier1_Products")
    issues = issues + _validate_products(PRODUCTS_WP5, "WP5_Tier2_Products")

    return issues
