OpenFOAM smoke case derived from the official cavity tutorial included in the
OpenFOAM 11 image.

This example keeps the standard `icoFoam` cavity structure and only reduces
`endTime` from `0.5` to `0.1` for faster validation.

Run it from the repository root:

```bash
cae docker pull openfoam-lite
cae docker run openfoam-lite examples/openfoam_cavity_smoke --cmd "bash -lc \"blockMesh && icoFoam\"" -o results/openfoam-cavity-smoke
```

Expected outputs include `constant/polyMesh/`, time directory `0.1/`, and
`docker-openfoam.log`.
