SU2 elasticity smoke example extracted from the local `su2-runtime` image and
verified through `cae docker run`.

Run it from the repository root:

```bash
cae docker build-su2-runtime --tag local/su2-runtime:8.3.0
cae docker run su2-runtime examples/su2_elasticity_smoke/case.cfg -o results/su2-smoke
```

Expected outputs include `history.csv`, `solution.dat`, and `docker-su2.log`.
