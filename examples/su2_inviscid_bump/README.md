Official SU2 CFD smoke case derived from `su2code/Tutorials` `v8.3.0`,
`compressible_flow/Inviscid_Bump`.

Files in this directory:

- `inv_channel.cfg`: preserved official tutorial configuration.
- `inv_channel_smoke.cfg`: smoke variant with `ITER= 50` for faster validation.
- `mesh_channel_256x128.su2`: official tutorial mesh.

Run it from the repository root:

```bash
cae docker build-su2-runtime --tag local/su2-runtime:8.3.0
cae docker run su2-runtime examples/su2_inviscid_bump/inv_channel_smoke.cfg -o results/su2-inviscid-bump-smoke
```

Validated outputs include `history.csv`, `restart_flow.dat`, `flow.vtu`, and
`docker-su2.log`.
