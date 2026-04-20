from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class DockerImageSpec:
    alias: str
    image: str
    solver: str
    command: list[str]
    description: str
    source: str
    input_type: str = "file"
    input_extensions: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    maturity: str = "stable"
    runnable: bool = True


_IMAGE_SPECS = [
    DockerImageSpec(
        alias="calculix",
        image="unifem/calculix-desktop:latest",
        solver="calculix",
        command=["ccx", "-i", "<job_name>"],
        description="Default CalculiX image for containerized ccx runs.",
        source="https://hub.docker.com/r/unifem/calculix-desktop",
        input_extensions=(".inp",),
        capabilities=("structural", "thermal", "fem", "linear", "nonlinear"),
    ),
    DockerImageSpec(
        alias="calculix-desktop",
        image="unifem/calculix-desktop:latest",
        solver="calculix",
        command=["ccx", "-i", "<job_name>"],
        description="UNIFEM CalculiX desktop image.",
        source="https://hub.docker.com/r/unifem/calculix-desktop",
        input_extensions=(".inp",),
        capabilities=("structural", "thermal", "fem", "linear", "nonlinear"),
    ),
    DockerImageSpec(
        alias="calculix-parallelworks",
        image="parallelworks/calculix:v2.15_exo",
        solver="calculix",
        command=["/opt/ccx-215/src/ccx_2.15", "-i", "<job_name>"],
        description="Parallel Works CalculiX image.",
        source="https://hub.docker.com/r/parallelworks/calculix",
        input_extensions=(".inp",),
        capabilities=("structural", "thermal", "fem", "linear", "nonlinear"),
    ),
    DockerImageSpec(
        alias="openfoam-ccx",
        image="unifem/openfoam-ccx:latest",
        solver="calculix",
        command=["ccx", "-i", "<job_name>"],
        description="OpenFOAM plus CalculiX image for future coupled workflows.",
        source="https://hub.docker.com/r/unifem/openfoam-ccx",
        input_extensions=(".inp",),
        capabilities=("structural", "thermal", "fem", "cfd-coupling"),
        maturity="community",
    ),
    DockerImageSpec(
        alias="code-aster",
        image="simvia/code_aster:stable",
        solver="code_aster",
        command=["run_aster", "<input_file>"],
        description="code_aster structural mechanics and thermomechanics solver.",
        source="https://hub.docker.com/r/simvia/code_aster",
        input_extensions=(".export",),
        capabilities=("structural", "thermal", "fem", "nonlinear", "contact", "dynamics"),
    ),
    DockerImageSpec(
        alias="code-aster-oldstable",
        image="simvia/code_aster:oldstable",
        solver="code_aster",
        command=["run_aster", "<input_file>"],
        description="Fallback code_aster image when the stable tag is unavailable through a mirror.",
        source="https://hub.docker.com/r/simvia/code_aster",
        input_extensions=(".export",),
        capabilities=("structural", "thermal", "fem", "nonlinear", "contact", "dynamics"),
        maturity="community",
    ),
    DockerImageSpec(
        alias="openfoam",
        image="openeuler/openfoam:2506-oe2403sp2",
        solver="openfoam",
        command=["simpleFoam"],
        description="OpenFOAM CFD toolbox image. Override --cmd for icoFoam, pimpleFoam, etc.",
        source="https://hub.docker.com/r/openeuler/openfoam",
        input_type="directory",
        capabilities=("cfd", "fluid", "turbulence", "heat-transfer", "multiphase"),
        maturity="community",
    ),
    DockerImageSpec(
        alias="openfoam-foundation-11",
        image="openfoam/openfoam11-paraview510",
        solver="openfoam",
        command=["bash", "-lc", "source /opt/openfoam11/etc/bashrc && simpleFoam"],
        description="OpenFOAM Foundation v11 fallback image with OpenFOAM environment setup.",
        source="https://hub.docker.com/r/openfoam/openfoam11-paraview510",
        input_type="directory",
        capabilities=("cfd", "fluid", "turbulence", "heat-transfer"),
        maturity="community",
    ),
    DockerImageSpec(
        alias="openfoam-lite",
        image="cfdengine/openfoam:latest",
        solver="openfoam",
        command=["bash", "-lc", "source /opt/openfoam6/etc/bashrc && simpleFoam"],
        description="Smaller community OpenFOAM fallback image for quick smoke tests.",
        source="https://hub.docker.com/r/cfdengine/openfoam",
        input_type="directory",
        capabilities=("cfd", "fluid", "turbulence"),
        maturity="community",
    ),
    DockerImageSpec(
        alias="su2-runtime",
        image="local/su2-runtime:8.3.0",
        solver="su2",
        command=["SU2_CFD", "<input_file>"],
        description="Locally built SU2 runtime image from cae docker build-su2-runtime.",
        source="local Docker build using conda-forge SU2",
        input_extensions=(".cfg",),
        capabilities=("cfd", "aerodynamics", "optimization", "adjoint"),
        maturity="local",
    ),
    DockerImageSpec(
        alias="su2",
        image="ghcr.io/su2code/su2/build-su2:250717-1402",
        solver="su2",
        command=["compileSU2.sh"],
        description="SU2 build container. It does not include a ready-to-run SU2_CFD executable.",
        source="https://github.com/orgs/su2code/packages/container/package/SU2%2Fbuild-su2",
        capabilities=("cfd", "aerodynamics", "optimization", "adjoint", "build-environment"),
        maturity="experimental",
        runnable=False,
    ),
    DockerImageSpec(
        alias="elmer",
        image="eperera/elmerfem:latest",
        solver="elmer",
        command=["ElmerSolver", "<input_file>"],
        description="Elmer FEM multiphysics solver image.",
        source="https://hub.docker.com/r/eperera/elmerfem",
        input_extensions=(".sif",),
        capabilities=("multiphysics", "thermal", "electromagnetics", "fluid", "structural", "fem"),
        maturity="community",
    ),
]

_IMAGE_BY_ALIAS = {spec.alias: spec for spec in _IMAGE_SPECS}
_IMAGE_BY_REFERENCE = {spec.image: spec for spec in _IMAGE_SPECS}


def list_image_specs(
    *,
    solver: str | None = None,
    capability: str | None = None,
    include_experimental: bool = True,
    runnable_only: bool = False,
) -> list[DockerImageSpec]:
    return [
        spec
        for spec in _IMAGE_SPECS
        if _matches_optional(spec.solver, solver)
        and _contains_optional(spec.capabilities, capability)
        and (include_experimental or spec.maturity != "experimental")
        and (not runnable_only or spec.runnable)
    ]


def list_image_spec_dicts(
    *,
    solver: str | None = None,
    capability: str | None = None,
    include_experimental: bool = True,
    runnable_only: bool = False,
) -> list[dict]:
    return [
        asdict(spec)
        for spec in list_image_specs(
            solver=solver,
            capability=capability,
            include_experimental=include_experimental,
            runnable_only=runnable_only,
        )
    ]


def get_image_spec(alias: str) -> DockerImageSpec | None:
    return _IMAGE_BY_ALIAS.get(alias.strip().lower())


def get_image_spec_for_reference(value: str) -> DockerImageSpec | None:
    raw = value.strip()
    return get_image_spec(raw) or _IMAGE_BY_REFERENCE.get(raw)


def resolve_image_reference(value: str) -> str:
    raw = value.strip()
    spec = get_image_spec(raw)
    return spec.image if spec else raw


def resolve_image_command(value: str, job_name: str) -> list[str]:
    spec = get_image_spec_for_reference(value)
    template = spec.command if spec else ["ccx", "-i", "<job_name>"]
    return render_command_template(template, job_name=job_name)


def render_command_template(
    template: Iterable[str],
    *,
    input_file: str | None = None,
    input_name: str | None = None,
    input_stem: str | None = None,
    job_name: str | None = None,
) -> list[str]:
    replacements = {
        "<input_file>": input_file or input_name or job_name or "",
        "<input_name>": input_name or input_file or job_name or "",
        "<input_stem>": input_stem or job_name or "",
        "<job_name>": job_name or input_stem or "",
        "<case_dir>": ".",
    }
    return [replacements.get(part, part) for part in template]


def solver_config_key(solver: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", solver.strip().lower()).strip("_")
    return f"docker_{normalized or 'solver'}_image"


def recommend_image_specs(
    query: str,
    *,
    limit: int = 5,
    runnable_only: bool = True,
) -> list[DockerImageSpec]:
    terms = _query_terms(query)
    if not terms:
        return []

    scored: list[tuple[int, DockerImageSpec]] = []
    for spec in _IMAGE_SPECS:
        if runnable_only and not spec.runnable:
            continue
        haystack = _query_terms(
            " ".join(
                [
                    spec.alias,
                    spec.solver,
                    spec.description,
                    spec.image,
                    " ".join(spec.capabilities),
                    " ".join(spec.input_extensions),
                ]
            )
        )
        score = len(terms & haystack) + _domain_bonus(terms, spec)
        if score <= 0:
            continue
        if spec.maturity == "stable":
            score += 1
        elif spec.maturity == "experimental":
            score -= 1
        scored.append((score, spec))

    scored.sort(key=lambda item: (-item[0], item[1].maturity != "stable", item[1].alias))
    return [spec for _, spec in scored[:limit]]


def _matches_optional(value: str, expected: str | None) -> bool:
    return expected is None or value.lower() == expected.strip().lower()


def _contains_optional(values: tuple[str, ...], expected: str | None) -> bool:
    return expected is None or expected.strip().lower() in {v.lower() for v in values}


def _query_terms(query: str) -> set[str]:
    aliases = {
        "fea": "fem",
        "finite": "fem",
        "mechanical": "structural",
        "mechanics": "structural",
        "solid": "structural",
        "stress": "structural",
        "fluid": "cfd",
        "flow": "cfd",
        "aero": "aerodynamics",
        "aerodynamic": "aerodynamics",
        "heat": "thermal",
        "temperature": "thermal",
        "em": "electromagnetics",
        "electromagnetic": "electromagnetics",
    }
    terms = set(re.findall(r"[a-z0-9_+.-]+", query.lower()))
    terms.update(aliases[t] for t in list(terms) if t in aliases)
    return terms


def _domain_bonus(terms: set[str], spec: DockerImageSpec) -> int:
    caps = {cap.lower() for cap in spec.capabilities}
    bonus = 0
    if {"structural", "fem"} & terms and {"structural", "fem"} & caps:
        bonus += 2
    if {"cfd", "aerodynamics"} & terms and {"cfd", "aerodynamics"} & caps:
        bonus += 2
    if {"thermal", "heat-transfer"} & terms and {"thermal", "heat-transfer"} & caps:
        bonus += 1
    if {"multiphysics", "electromagnetics"} & terms and {"multiphysics", "electromagnetics"} & caps:
        bonus += 2
    return bonus
